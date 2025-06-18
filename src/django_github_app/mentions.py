from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from gidgethub import sansio

from .permissions import Permission


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


@dataclass
class MentionContext:
    commands: list[str]
    user_permission: Permission | None
    scope: MentionScope | None


class MentionMatch(NamedTuple):
    mention: str
    command: str | None


CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")
QUOTE_PATTERN = re.compile(r"^\s*>.*$", re.MULTILINE)


def parse_mentions(event: sansio.Event, username: str) -> list[MentionMatch]:
    text = event.data.get("comment", {}).get("body", "")

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


def get_commands(event: sansio.Event, username: str) -> list[str]:
    mentions = parse_mentions(event, username)
    return [m.command for m in mentions if m.command]


def check_event_for_mention(
    event: sansio.Event, command: str | None, username: str
) -> bool:
    mentions = parse_mentions(event, username)

    if not mentions:
        return False

    if not command:
        return True

    return any(mention.command == command.lower() for mention in mentions)


def get_event_scope(event: sansio.Event) -> MentionScope | None:
    if event.event == "issue_comment":
        issue = event.data.get("issue", {})
        is_pull_request = "pull_request" in issue and issue["pull_request"] is not None
        return MentionScope.PR if is_pull_request else MentionScope.ISSUE

    for scope in MentionScope:
        scope_events = scope.get_events()
        if any(event_action.event == event.event for event_action in scope_events):
            return scope

    return None
