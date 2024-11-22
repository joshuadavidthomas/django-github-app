from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any
from typing import TypeVar

from django.utils.functional import classproperty
from gidgethub import sansio
from gidgethub.routing import Router as GidgetHubRouter

from ._typing import override

AsyncCallback = Callable[..., Awaitable[None]]
SyncCallback = Callable[..., None]

CB = TypeVar("CB", AsyncCallback, SyncCallback)


class GitHubRouter(GidgetHubRouter):
    _routers: list[GidgetHubRouter] = []
    _library_handlers_loaded = False

    def __init__(self, *args) -> None:
        super().__init__(*args)
        GitHubRouter._routers.append(self)

    @classmethod
    def _load_library_handlers(cls):
        if cls._library_handlers_loaded:
            return

        from .checks import get_webhook_views
        from .views import AsyncWebhookView

        views = get_webhook_views()
        if views and issubclass(views[0], AsyncWebhookView):
            from .events import ahandlers  # noqa: F401
        else:
            from .events import handlers  # noqa: F401

        cls._library_handlers_loaded = True

    @classproperty
    def routers(cls):
        cls._load_library_handlers()
        return list(cls._routers)

    def event(self, event_type: str, **kwargs: Any) -> Callable[[CB], CB]:
        def decorator(func: CB) -> CB:
            self.add(func, event_type, **kwargs)  # type: ignore[arg-type]
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
