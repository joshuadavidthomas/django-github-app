# Plan for Issue #38: Auto-load internal library webhook events based on async/sync view

## 1. Summary

Currently, `django-github-app` loads webhook event handlers based on the `WEBHOOK_TYPE` setting defined in the Django settings. This loading occurs within the `GitHubAppConfig.ready()` method when the Django application starts. Specifically:
- If `WEBHOOK_TYPE` is `"async"`, it imports `django_github_app.events.ahandlers`.
- If `WEBHOOK_TYPE` is `"sync"`, it imports `django_github_app.events.handlers`.

This approach has drawbacks:
- It loads *all* handlers of the specified type (async or sync) at application startup, regardless of whether they are immediately needed or if the corresponding view (`AsyncWebhookView` or `SyncWebhookView`) is even configured in the URL patterns.
- It tightly couples the handler loading mechanism to a global setting and the app's `ready()` method, which might not be flexible enough for all use cases (as noted in issue #38).
- If a project potentially uses *both* async and sync views (perhaps for different endpoints), the current mechanism only allows loading one type of handler.

The goal is to decouple handler loading from `AppConfig.ready()` and the `WEBHOOK_TYPE` setting. Instead, the loading should happen dynamically (just-in-time) based on the actual view being invoked:
- When `AsyncWebhookView` handles a request, ensure the async handlers (`.events.ahandlers`) are loaded.
- When `SyncWebhookView` handles a request, ensure the sync handlers (`.events.handlers`) are loaded.
- Loading should be idempotent (i.e., handlers should only be loaded once per type, even across multiple requests).

## 2. Proposed Solution

We will implement a lazy-loading mechanism triggered within the respective webhook views (`AsyncWebhookView` and `SyncWebhookView`).

1.  **Remove Startup Loading:** Eliminate the handler import logic from `GitHubAppConfig.ready()`.
2.  **Introduce Loading Logic in Router:** Add class-level mechanisms to `GitHubRouter` to manage the loading state of async and sync handlers. This will involve:
    *   Boolean flags (`_async_handlers_loaded`, `_sync_handlers_loaded`) to track whether the respective handlers have been loaded.
    *   Thread locks (`_async_load_lock`, `_sync_load_lock`) to ensure thread-safe loading in concurrent environments.
    *   Class methods (`ensure_async_handlers_loaded`, `ensure_sync_handlers_loaded`) that check the flags, acquire the lock, perform the import using `importlib.import_module` if not already loaded, and update the flag. Importing the modules (`.events.ahandlers` or `.events.handlers`) will trigger the `@gh.event` decorators, which register the handlers by instantiating `GitHubRouter` instances (which are added to the global `GitHubRouter._routers` list).
3.  **Trigger Loading from Views:** Modify the `post` methods of `AsyncWebhookView` and `SyncWebhookView` to call the corresponding `ensure_..._loaded` method on `GitHubRouter` *before* dispatching the event.
4.  **Dispatching:** The existing `self.router` property in the views, which aggregates all globally registered routers via `GitHubRouter.routers`, will remain effective. It will collect all routers, including those registered during the lazy loading process, allowing `adispatch` or `dispatch` to find the correct handlers.

This approach ensures that handlers are only loaded when the relevant view is first used, and the loading process is thread-safe and idempotent.

## 3. Code Changes Needed

*   **`src/django_github_app/apps.py`**:
    *   Remove the conditional import of `.events.ahandlers` and `.events.handlers` from the `ready()` method.
    *   Remove the dependency on `app_settings.WEBHOOK_TYPE` for handler loading.

*   **`src/django_github_app/routing.py`**:
    *   Import `importlib` and `threading`.
    *   Add class attributes to `GitHubRouter`:
        *   `_async_handlers_loaded: bool = False`
        *   `_sync_handlers_loaded: bool = False`
        *   `_async_load_lock = threading.Lock()`
        *   `_sync_load_lock = threading.Lock()`
    *   Add class method `ensure_async_handlers_loaded(cls)`:
        *   Check `if not cls._async_handlers_loaded:`.
        *   Acquire `cls._async_load_lock`.
        *   Re-check `if not cls._async_handlers_loaded:` (double-checked locking).
        *   `importlib.import_module(".events.ahandlers", package="django_github_app")`
        *   Set `cls._async_handlers_loaded = True`.
        *   Release lock (using a `with` statement is preferred).
    *   Add class method `ensure_sync_handlers_loaded(cls)`:
        *   Similar logic as above, but using `_sync_handlers_loaded`, `_sync_load_lock`, and importing `.events.handlers`.

*   **`src/django_github_app/views.py`**:
    *   In `AsyncWebhookView.post`:
        *   Add `GitHubRouter.ensure_async_handlers_loaded()` before the line `await self.router.adispatch(event, gh)`.
    *   In `SyncWebhookView.post`:
        *   Add `GitHubRouter.ensure_sync_handlers_loaded()` before the line `self.router.dispatch(event, gh)`.

## 4. Considerations and Implications

*   **Thread Safety:** The use of `threading.Lock` ensures that even if multiple requests hit the same view concurrently for the first time, the import process happens only once, preventing race conditions.
*   **Import Side Effects:** This solution relies on the side effect of importing the `ahandlers` or `handlers` modules: the execution of `@gh.event` decorators which register the handler functions with instances of `GitHubRouter`. This matches the current behavior, just deferred.
*   **Testing:** Tests need to be updated or added to verify:
    *   Handlers are not loaded if neither view is used.
    *   Async handlers are loaded only when `AsyncWebhookView` is used.
    *   Sync handlers are loaded only when `SyncWebhookView` is used.
    *   Loading is idempotent.
    *   Events are correctly dispatched to the lazily loaded handlers.
*   **Flexibility:** This approach allows projects to potentially mix `AsyncWebhookView` and `SyncWebhookView` in the same project (e.g., mapped to different URL endpoints), as each view will load its required handlers independently.
*   **Readability:** Tying the loading logic to the view that requires the handlers arguably makes the control flow clearer compared to loading everything based on a global setting at startup.
*   **`WEBHOOK_TYPE` Setting:** The `app_settings.WEBHOOK_TYPE` setting becomes obsolete *for the purpose of handler loading*. It might still be used elsewhere, but its primary role is removed. We should consider deprecating or removing it if it has no other uses. (For now, we will just stop using it for loading).
