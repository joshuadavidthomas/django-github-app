from __future__ import annotations

import re
from enum import Enum
from typing import Any
from typing import NamedTuple


class EventAction(NamedTuple):
    event: str
    action: str


class CommandScope(str, Enum):
    COMMIT = "commit"
    ISSUE = "issue"
    PR = "pr"

    def get_events(self) -> list[EventAction]:
        match self:
            case CommandScope.ISSUE:
                return [
                    EventAction("issue_comment", "created"),
                ]
            case CommandScope.PR:
                return [
                    EventAction("issue_comment", "created"),
                    EventAction("pull_request_review_comment", "created"),
                    EventAction("pull_request_review", "submitted"),
                ]
            case CommandScope.COMMIT:
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


class MentionMatch(NamedTuple):
    mention: str
    command: str | None


CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")
QUOTE_PATTERN = re.compile(r"^\s*>.*$", re.MULTILINE)


def parse_mentions(text: str, username: str) -> list[MentionMatch]:
    if not text:
        return []

    text = CODE_BLOCK_PATTERN.sub(lambda m: " " * len(m.group(0)), text)
    text = INLINE_CODE_PATTERN.sub(lambda m: " " * len(m.group(0)), text)
    text = QUOTE_PATTERN.sub(lambda m: " " * len(m.group(0)), text)

    username_pattern = re.compile(
        rf"(?:^|(?<=\s))(@{re.escape(username)})(?:\s+([\w\-?]+))?(?=\s|$|[^\w\-])",
        re.MULTILINE | re.IGNORECASE,
    )

    mentions: list[MentionMatch] = []
    for match in username_pattern.finditer(text):
        mention = match.group(1)  # @username
        command = match.group(2)  # optional command
        mentions.append(
            MentionMatch(mention=mention, command=command.lower() if command else None)
        )

    return mentions


def check_event_for_mention(
    event: dict[str, Any], command: str | None, username: str
) -> bool:
    comment = event.get("comment", {}).get("body", "")
    mentions = parse_mentions(comment, username)

    if not mentions:
        return False

    if not command:
        return True

    return any(mention.command == command.lower() for mention in mentions)
