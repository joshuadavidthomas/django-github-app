from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.utils.functional import classproperty
from gidgethub.routing import AsyncCallback
from gidgethub.routing import Router as GidgetHubRouter


class GitHubRouter:
    _routers: list[GidgetHubRouter] = []

    def __init__(self) -> None:
        self.router = GidgetHubRouter()
        GitHubRouter._routers.append(self.router)

    @classproperty
    def routers(cls):
        return list(cls._routers)

    def event(
        self, event_type: str, **kwargs: Any
    ) -> Callable[[AsyncCallback], AsyncCallback]:
        def decorator(func: AsyncCallback) -> AsyncCallback:
            self.router.add(func, event_type, **kwargs)
            return func

        return decorator
