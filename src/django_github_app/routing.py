from __future__ import annotations

import importlib
import threading
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

    # Class-level state for lazy loading handlers
    _async_handlers_loaded: bool = False
    _sync_handlers_loaded: bool = False
    _async_load_lock = threading.Lock()
    _sync_load_lock = threading.Lock()

    def __init__(self, *args) -> None:
        super().__init__(*args)
        # Ensure this instance is registered *before* potentially triggering loading
        # in subclasses or specific use cases, although typical registration happens
        # via the @gh.event decorator upon module import.
        if self not in GitHubRouter._routers:
            GitHubRouter._routers.append(self)

    @classproperty
    def routers(cls):
        # Ensure handlers are loaded based on which view might be calling this.
        # While the views explicitly call ensure_..._loaded, accessing routers
        # directly elsewhere might implicitly expect handlers to be loaded.
        # However, explicitly calling ensure in views is the primary mechanism.
        return list(cls._routers)

    @classmethod
    def ensure_async_handlers_loaded(cls):
        """Lazily load async handlers in a thread-safe manner."""
        if not cls._async_handlers_loaded:
            with cls._async_load_lock:
                # Double-check locking pattern
                if not cls._async_handlers_loaded:
                    importlib.import_module(
                        ".events.ahandlers", package="django_github_app"
                    )
                    cls._async_handlers_loaded = True

    @classmethod
    def ensure_sync_handlers_loaded(cls):
        """Lazily load sync handlers in a thread-safe manner."""
        if not cls._sync_handlers_loaded:
            with cls._sync_load_lock:
                # Double-check locking pattern
                if not cls._sync_handlers_loaded:
                    importlib.import_module(
                        ".events.handlers", package="django_github_app"
                    )
                    cls._sync_handlers_loaded = True

    def event(self, event_type: str, **kwargs: Any) -> Callable[[CB], CB]:
        def decorator(func: CB) -> CB:
            self.add(func, event_type, **kwargs)  # type: ignore[arg-type]
            # Ensure the router instance used by the decorator is registered globally
            if self not in GitHubRouter._routers:
                 GitHubRouter._routers.append(self) # pragma: no cover
            return func

        return decorator

    async def adispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:
        """Dispatch event to all registered async callbacks."""
        # Note: self.fetch(event) finds callbacks *only* on this specific router instance.
        # We need to iterate through all globally registered routers.
        found_callbacks = []
        for router in self.routers:
            found_callbacks.extend(router.fetch(event))

        for callback in found_callbacks:
            # Assuming callbacks are async, as this is adispatch
            await callback(event, *args, **kwargs)

    @override
    def dispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        """Dispatch event to all registered sync callbacks."""
        # Note: self.fetch(event) finds callbacks *only* on this specific router instance.
        # We need to iterate through all globally registered routers.
        found_callbacks = []
        for router in self.routers:
            found_callbacks.extend(router.fetch(event))

        for callback in found_callbacks:
            # Assuming callbacks are sync, as this is dispatch
            callback(event, *args, **kwargs)
