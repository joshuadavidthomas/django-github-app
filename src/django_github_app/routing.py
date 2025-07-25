from __future__ import annotations

import re
from asyncio import iscoroutinefunction
from collections.abc import Awaitable
from collections.abc import Callable
from functools import wraps
from typing import Any
from typing import Protocol
from typing import TypeVar
from typing import cast

from django.utils.functional import classproperty
from gidgethub import sansio
from gidgethub.routing import Router as GidgetHubRouter

from ._typing import override
from .github import AsyncGitHubAPI
from .github import SyncGitHubAPI
from .mentions import Mention
from .mentions import MentionScope

AsyncCallback = Callable[..., Awaitable[None]]
SyncCallback = Callable[..., None]

CB = TypeVar("CB", AsyncCallback, SyncCallback)


class AsyncMentionHandler(Protocol):
    async def __call__(
        self, event: sansio.Event, *args: Any, **kwargs: Any
    ) -> None: ...


class SyncMentionHandler(Protocol):
    def __call__(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None: ...


MentionHandler = AsyncMentionHandler | SyncMentionHandler


class GitHubRouter(GidgetHubRouter):
    _routers: list[GidgetHubRouter] = []

    def __init__(self, *args) -> None:
        super().__init__(*args)
        GitHubRouter._routers.append(self)

    @override
    def add(
        self, func: AsyncCallback | SyncCallback, event_type: str, **data_detail: Any
    ) -> None:
        # Override to accept both async and sync callbacks.
        super().add(cast(AsyncCallback, func), event_type, **data_detail)

    @classproperty
    def routers(cls):
        return list(cls._routers)

    def event(self, event_type: str, **kwargs: Any) -> Callable[[CB], CB]:
        def decorator(func: CB) -> CB:
            self.add(func, event_type, **kwargs)
            return func

        return decorator

    def mention(
        self,
        *,
        username: str | re.Pattern[str] | None = None,
        scope: MentionScope | None = None,
        **kwargs: Any,
    ) -> Callable[[CB], CB]:
        def decorator(func: CB) -> CB:
            @wraps(func)
            async def async_wrapper(
                event: sansio.Event, gh: AsyncGitHubAPI, *args: Any, **kwargs: Any
            ) -> None:
                event_scope = MentionScope.from_event(event)
                if scope is not None and event_scope != scope:
                    return

                for mention in Mention.from_event(
                    event, username=username, scope=event_scope
                ):
                    await func(event, gh, *args, context=mention, **kwargs)  # type: ignore[func-returns-value]

            @wraps(func)
            def sync_wrapper(
                event: sansio.Event, gh: SyncGitHubAPI, *args: Any, **kwargs: Any
            ) -> None:
                event_scope = MentionScope.from_event(event)
                if scope is not None and event_scope != scope:
                    return

                for mention in Mention.from_event(
                    event, username=username, scope=event_scope
                ):
                    func(event, gh, *args, context=mention, **kwargs)

            wrapper: MentionHandler
            if iscoroutinefunction(func):
                wrapper = cast(AsyncMentionHandler, async_wrapper)
            else:
                wrapper = cast(SyncMentionHandler, sync_wrapper)

            events = scope.get_events() if scope else MentionScope.all_events()
            for event_action in events:
                self.add(
                    wrapper, event_action.event, action=event_action.action, **kwargs
                )

            return func

        return decorator

    async def adispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:
        found_callbacks = self.fetch(event)
        for callback in found_callbacks:
            await callback(event, *args, **kwargs)

    @override
    def dispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        found_callbacks = self.fetch(event)
        for callback in found_callbacks:
            callback(event, *args, **kwargs)
