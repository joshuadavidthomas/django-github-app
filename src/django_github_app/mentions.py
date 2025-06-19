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
        """Determine the scope of a GitHub event based on its type and context."""
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
class Mention:
    username: str
    text: str
    position: int
    line_number: int
    line_text: str
    match: re.Match[str] | None = None
    previous_mention: Mention | None = None
    next_mention: Mention | None = None


@dataclass
class Comment:
    body: str
    author: str
    created_at: datetime
    url: str
    mentions: list[Mention]

    @property
    def line_count(self) -> int:
        """Number of lines in the comment."""
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

        created_at_str = comment_data.get("created_at", "")
        if created_at_str:
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
class MentionEvent:
    comment: Comment
    triggered_by: Mention
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
        """Generate MentionEvent instances from a GitHub event.

        Yields MentionEvent for each mention that matches the given criteria.
        """
        # Check scope match first
        event_scope = MentionScope.from_event(event)
        if scope is not None and event_scope != scope:
            return

        # Parse mentions
        mentions = parse_mentions_for_username(event, username)
        if not mentions:
            return

        # Create comment
        comment = Comment.from_event(event)
        comment.mentions = mentions

        # Yield contexts for matching mentions
        for mention in mentions:
            # Check pattern match if specified
            if pattern is not None:
                match = check_pattern_match(mention.text, pattern)
                if not match:
                    continue
                mention.match = match

            yield cls(
                comment=comment,
                triggered_by=mention,
                scope=event_scope,
            )


CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")
QUOTE_PATTERN = re.compile(r"^\s*>.*$", re.MULTILINE)


def check_pattern_match(
    text: str, pattern: str | re.Pattern[str] | None
) -> re.Match[str] | None:
    """Check if text matches the given pattern (string or regex).

    Returns Match object if pattern matches, None otherwise.
    If pattern is None, returns a dummy match object.
    """
    if pattern is None:
        return re.match(r"(.*)", text, re.IGNORECASE | re.DOTALL)

    # Check if it's a compiled regex pattern
    if isinstance(pattern, re.Pattern):
        # Use the pattern directly, preserving its flags
        return pattern.match(text)

    # For strings, do exact match (case-insensitive)
    # Escape the string to treat it literally
    escaped_pattern = re.escape(pattern)
    return re.match(escaped_pattern, text, re.IGNORECASE)


def parse_mentions_for_username(
    event: sansio.Event, username_pattern: str | re.Pattern[str] | None = None
) -> list[Mention]:
    comment = event.data.get("comment", {})
    if comment is None:
        comment = {}
    body = comment.get("body", "")

    if not body:
        return []

    # If no pattern specified, use bot username (TODO: get from settings)
    if username_pattern is None:
        username_pattern = "bot"  # Placeholder

    # Handle regex patterns vs literal strings
    if isinstance(username_pattern, re.Pattern):
        # Use the pattern string directly, preserving any flags
        username_regex = username_pattern.pattern
        # Extract flags from the compiled pattern
        flags = username_pattern.flags | re.MULTILINE | re.IGNORECASE
    else:
        # For strings, escape them to be treated literally
        username_regex = re.escape(username_pattern)
        flags = re.MULTILINE | re.IGNORECASE

    original_body = body
    original_lines = original_body.splitlines()

    processed_text = CODE_BLOCK_PATTERN.sub(lambda m: " " * len(m.group(0)), body)
    processed_text = INLINE_CODE_PATTERN.sub(
        lambda m: " " * len(m.group(0)), processed_text
    )
    processed_text = QUOTE_PATTERN.sub(lambda m: " " * len(m.group(0)), processed_text)

    # Use \S+ to match non-whitespace characters for username
    # Special handling for patterns that could match too broadly
    if ".*" in username_regex:
        # Replace .* with a more specific pattern that won't match spaces or @
        username_regex = username_regex.replace(".*", r"[^@\s]*")

    mention_pattern = re.compile(
        rf"(?:^|(?<=\s))@({username_regex})(?:\s|$|(?=[^\w\-]))",
        flags,
    )

    mentions: list[Mention] = []

    for match in mention_pattern.finditer(processed_text):
        position = match.start()  # Position of @
        username = match.group(1)  # Captured username

        text_before = original_body[:position]
        line_number = text_before.count("\n") + 1

        line_index = line_number - 1
        line_text = (
            original_lines[line_index] if line_index < len(original_lines) else ""
        )

        text_start = match.end()

        # Find next @mention to know where this text ends
        next_match = mention_pattern.search(processed_text, match.end())
        if next_match:
            text_end = next_match.start()
        else:
            text_end = len(original_body)

        text = original_body[text_start:text_end].strip()

        mention = Mention(
            username=username,
            text=text,
            position=position,
            line_number=line_number,
            line_text=line_text,
            match=None,
            previous_mention=None,
            next_mention=None,
        )

        mentions.append(mention)

    for i, mention in enumerate(mentions):
        if i > 0:
            mention.previous_mention = mentions[i - 1]
        if i < len(mentions) - 1:
            mention.next_mention = mentions[i + 1]

    return mentions
