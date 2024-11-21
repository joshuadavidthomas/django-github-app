from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.utils.functional import classproperty
from gidgethub import sansio
from gidgethub.routing import AsyncCallback
from gidgethub.routing import Router as GidgetHubRouter

from ._typing import override


class GitHubRouter(GidgetHubRouter):
    _routers: list[GidgetHubRouter] = []

    def __init__(self, *args) -> None:
        super().__init__(*args)
        GitHubRouter._routers.append(self)

    @classproperty
    def routers(cls):
        return list(cls._routers)

    def event(
        self, event_type: str, **kwargs: Any
    ) -> Callable[[AsyncCallback], AsyncCallback]:
        def decorator(func: AsyncCallback) -> AsyncCallback:
            self.add(func, event_type, **kwargs)
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
