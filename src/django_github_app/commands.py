from __future__ import annotations

from enum import Enum
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

