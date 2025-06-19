from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import NamedTuple

from django.conf import settings
from django.utils import timezone
from gidgethub import sansio


class EventAction(NamedTuple):
    event: str
    action: str


class MentionScope(str, Enum):
    COMMIT = "commit"
    ISSUE = "issue"
    PR = "pr"

    def get_events(self) -> list[EventAction]:
        match self:
            case MentionScope.ISSUE:
                return [
                    EventAction("issue_comment", "created"),
                ]
            case MentionScope.PR:
                return [
                    EventAction("issue_comment", "created"),
                    EventAction("pull_request_review_comment", "created"),
                    EventAction("pull_request_review", "submitted"),
                ]
            case MentionScope.COMMIT:
                return [
                    EventAction("commit_comment", "created"),
                ]

    @classmethod
    def all_events(cls) -> list[EventAction]:
        return list(
            dict.fromkeys(
                event_action for scope in cls for event_action in scope.get_events()
            )
        )

    @classmethod
    def from_event(cls, event: sansio.Event) -> MentionScope | None:
        if event.event == "issue_comment":
            issue = event.data.get("issue", {})
            is_pull_request = (
                "pull_request" in issue and issue["pull_request"] is not None
            )
            return cls.PR if is_pull_request else cls.ISSUE

        for scope in cls:
            scope_events = scope.get_events()
            if any(event_action.event == event.event for event_action in scope_events):
                return scope

        return None


@dataclass
class RawMention:
    match: re.Match[str]
    username: str
    position: int
    end: int


CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")
BLOCKQUOTE_PATTERN = re.compile(r"^\s*>.*$", re.MULTILINE)


# GitHub username rules:
# - 1-39 characters long
# - Can only contain alphanumeric characters or hyphens
# - Cannot start or end with a hyphen
# - Cannot have multiple consecutive hyphens
GITHUB_MENTION_PATTERN = re.compile(
    r"(?:^|(?<=\s))@([a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38})",
    re.MULTILINE | re.IGNORECASE,
)


def extract_all_mentions(text: str) -> list[RawMention]:
    # replace all code blocks, inline code, and blockquotes with spaces
    # this preserves linenos and postitions while not being able to
    # match against anything in them
    processed_text = CODE_BLOCK_PATTERN.sub(lambda m: " " * len(m.group(0)), text)
    processed_text = INLINE_CODE_PATTERN.sub(
        lambda m: " " * len(m.group(0)), processed_text
    )
    processed_text = BLOCKQUOTE_PATTERN.sub(
        lambda m: " " * len(m.group(0)), processed_text
    )
    return [
        RawMention(
            match=match,
            username=match.group(1),
            position=match.start(),
            end=match.end(),
        )
        for match in GITHUB_MENTION_PATTERN.finditer(processed_text)
    ]


class LineInfo(NamedTuple):
    lineno: int
    text: str

    @classmethod
    def for_mention_in_comment(cls, comment: str, mention_position: int):
        lines = comment.splitlines()
        text_before = comment[:mention_position]
        line_number = text_before.count("\n") + 1

        line_index = line_number - 1
        line_text = lines[line_index] if line_index < len(lines) else ""

        return cls(lineno=line_number, text=line_text)


def extract_mention_text(
    body: str, current_index: int, all_mentions: list[RawMention], mention_end: int
) -> str:
    text_start = mention_end

    # Find next @mention (any mention, not just matched ones) to know where this text ends
    next_mention_index = None
    for j in range(current_index + 1, len(all_mentions)):
        next_mention_index = j
        break

    if next_mention_index is not None:
        text_end = all_mentions[next_mention_index].position
    else:
        text_end = len(body)

    return body[text_start:text_end].strip()


@dataclass
class ParsedMention:
    username: str
    text: str
    position: int
    line_info: LineInfo
    match: re.Match[str] | None = None
    previous_mention: ParsedMention | None = None
    next_mention: ParsedMention | None = None


def extract_mentions_from_event(
    event: sansio.Event, username_pattern: str | re.Pattern[str] | None = None
) -> list[ParsedMention]:
    comment_data = event.data.get("comment", {})
    if comment_data is None:
        comment_data = {}
    comment = comment_data.get("body", "")

    if not comment:
        return []

    # If no pattern specified, use bot username (TODO: get from settings)
    if username_pattern is None:
        username_pattern = "bot"  # Placeholder

    mentions: list[ParsedMention] = []
    potential_mentions = extract_all_mentions(comment)
    for i, raw_mention in enumerate(potential_mentions):
        if not matches_pattern(raw_mention.username, username_pattern):
            continue

        text = extract_mention_text(comment, i, potential_mentions, raw_mention.end)
        line_info = LineInfo.for_mention_in_comment(comment, raw_mention.position)

        mentions.append(
            ParsedMention(
                username=raw_mention.username,
                text=text,
                position=raw_mention.position,
                line_info=line_info,
                match=None,
                previous_mention=None,
                next_mention=None,
            )
        )

    # link mentions
    for i, mention in enumerate(mentions):
        if i > 0:
            mention.previous_mention = mentions[i - 1]
        if i < len(mentions) - 1:
            mention.next_mention = mentions[i + 1]

    return mentions


@dataclass
class Comment:
    body: str
    author: str
    created_at: datetime
    url: str
    mentions: list[ParsedMention]

    @property
    def line_count(self) -> int:
        if not self.body:
            return 0
        return len(self.body.splitlines())

    @classmethod
    def from_event(cls, event: sansio.Event) -> Comment:
        match event.event:
            case "issue_comment" | "pull_request_review_comment" | "commit_comment":
                comment_data = event.data.get("comment")
            case "pull_request_review":
                comment_data = event.data.get("review")
            case _:
                comment_data = None

        if not comment_data:
            raise ValueError(f"Cannot extract comment from event type: {event.event}")

        if created_at_str := comment_data.get("created_at", ""):
            # GitHub timestamps are in ISO format: 2024-01-01T12:00:00Z
            created_at_aware = datetime.fromisoformat(
                created_at_str.replace("Z", "+00:00")
            )
            if settings.USE_TZ:
                created_at = created_at_aware
            else:
                created_at = timezone.make_naive(
                    created_at_aware, timezone.get_default_timezone()
                )
        else:
            created_at = timezone.now()

        author = comment_data.get("user", {}).get("login", "")
        if not author and "sender" in event.data:
            author = event.data.get("sender", {}).get("login", "")

        return cls(
            body=comment_data.get("body", ""),
            author=author,
            created_at=created_at,
            url=comment_data.get("html_url", ""),
            mentions=[],
        )


@dataclass
class Mention:
    comment: Comment
    mention: ParsedMention
    scope: MentionScope | None

    @classmethod
    def from_event(
        cls,
        event: sansio.Event,
        *,
        username: str | re.Pattern[str] | None = None,
        pattern: str | re.Pattern[str] | None = None,
        scope: MentionScope | None = None,
    ):
        event_scope = MentionScope.from_event(event)
        if scope is not None and event_scope != scope:
            return

        mentions = extract_mentions_from_event(event, username)
        if not mentions:
            return

        comment = Comment.from_event(event)
        comment.mentions = mentions

        for mention in mentions:
            if pattern is not None:
                match = get_match(mention.text, pattern)
                if not match:
                    continue
                mention.match = match

            yield cls(
                comment=comment,
                mention=mention,
                scope=event_scope,
            )


def matches_pattern(text: str, pattern: str | re.Pattern[str] | None) -> bool:
    match pattern:
        case None:
            return True
        case re.Pattern():
            return pattern.fullmatch(text) is not None
        case str():
            return text.strip().lower() == pattern.strip().lower()


def get_match(text: str, pattern: str | re.Pattern[str] | None) -> re.Match[str] | None:
    match pattern:
        case None:
            return re.match(r"(.*)", text, re.IGNORECASE | re.DOTALL)
        case re.Pattern():
            # Use the pattern directly, preserving its flags
            return pattern.match(text)
        case str():
            # For strings, do exact match (case-insensitive)
            # Escape the string to treat it literally
            return re.match(re.escape(pattern), text, re.IGNORECASE)
