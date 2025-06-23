from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

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


@dataclass
class ParsedMention:
    username: str
    position: int
    line_info: LineInfo
    previous_mention: ParsedMention | None = None
    next_mention: ParsedMention | None = None


def matches_pattern(text: str, pattern: str | re.Pattern[str]) -> bool:
    match pattern:
        case re.Pattern():
            return pattern.fullmatch(text) is not None
        case str():
            return text.strip().lower() == pattern.strip().lower()


def extract_mentions_from_event(
    event: sansio.Event, username_pattern: str | re.Pattern[str] | None = None
) -> list[ParsedMention]:
    comment_key = "comment" if event.event != "pull_request_review" else "review"
    comment = event.data.get(comment_key, {}).get("body", "")

    if not comment:
        return []

    mentions: list[ParsedMention] = []
    potential_mentions = extract_all_mentions(comment)
    for raw_mention in potential_mentions:
        if username_pattern and not matches_pattern(
            raw_mention.username, username_pattern
        ):
            continue

        mentions.append(
            ParsedMention(
                username=raw_mention.username,
                position=raw_mention.position,
                line_info=LineInfo.for_mention_in_comment(
                    comment, raw_mention.position
                ),
                previous_mention=None,
                next_mention=None,
            )
        )

    for i, mention in enumerate(mentions):
        if i > 0:
            mention.previous_mention = mentions[i - 1]
        if i < len(mentions) - 1:
            mention.next_mention = mentions[i + 1]

    return mentions


@dataclass
class Mention:
    mention: ParsedMention
    scope: MentionScope | None

    @classmethod
    def from_event(
        cls,
        event: sansio.Event,
        *,
        username: str | re.Pattern[str] | None = None,
        scope: MentionScope | None = None,
    ):
        mentions = extract_mentions_from_event(event, username)
        for mention in mentions:
            yield cls(mention=mention, scope=scope)
