# Django GitHub App - Development Plan

This document outlines the implementation plan for the open issues in the django-github-app project.

## Overview

We will be addressing the following issues:

1. [Issue #47](https://github.com/joshuadavidthomas/django-github-app/issues/47): Documentation of using `AsyncGitHubAPI`/`SyncGithubAPI` incorrect
2. [Issue #38](https://github.com/joshuadavidthomas/django-github-app/issues/38): Auto-load internal library webhook events based on async/sync view
3. [Issue #22](https://github.com/joshuadavidthomas/django-github-app/issues/22): Add delete/archive `EventLog` action to admin
4. [Issue #17](https://github.com/joshuadavidthomas/django-github-app/issues/17): Add ability to archive `EventLog` instances
5. [Issue #15](https://github.com/joshuadavidthomas/django-github-app/issues/15): Allow for defining command callbacks, for issue/PR comments containing @ the github app

The implementation will be done in order of complexity, starting with simpler documentation fixes and then moving to more complex features.

---

# Plan for Issue #47: Documentation of using `AsyncGitHubAPI`/`SyncGithubAPI` incorrect

**Description**: Fix the documentation of `AsyncGitHubAPI`/`SyncGithubAPI` to correctly show that the `requester` parameter is required.

**Approach**: Update the README.md examples to include the `requester` parameter in all uses of `AsyncGitHubAPI` and `SyncGitHubAPI`. Alternatively, consider implementing a default value for the `requester` parameter using `app_settings.SLUG`.

---

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

# Plan for Issue #22: Add delete/archive `EventLog` action to admin

## 1. Summary

The `EventLog` model in django-github-app is used to store webhook events received from GitHub. The model already has built-in functionality for cleaning up old events through the `acleanup_events`/`cleanup_events` manager methods, which delete events older than a specified number of days (determined by the `DAYS_TO_KEEP_EVENTS` setting, defaulting to 7 days).

Currently, this cleanup is either triggered automatically during webhook processing (if `AUTO_CLEANUP_EVENTS` is set to `True` in settings) or must be manually invoked through code. Issue #22 requests adding a "Clean-up Events" action to the Django admin interface to allow administrators to manually trigger the cleanup process with a single click.

There's also a note about potential future archiving functionality (related to issue #17), but the immediate focus is on implementing the deletion action.

## 2. Proposed Solution

We will add a custom admin action to the `EventLogModelAdmin` class that allows administrators to clean up old events directly from the admin interface. This solution will:

1. Add a new action method to `EventLogModelAdmin` that invokes the existing `cleanup_events` method on the `EventLog` manager.
2. Include a confirmation page that shows how many events will be deleted, with the default threshold set to the value from `DAYS_TO_KEEP_EVENTS`.
3. Allow administrators to adjust the threshold (days to keep) on the confirmation page.
4. Support both async and sync Django environments.

## 3. Code Changes Needed

We need to modify `src/django_github_app/admin.py` to add the cleanup action to the `EventLogModelAdmin`:

```python
from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from asgiref.sync import async_to_sync, sync_to_async

from .conf import app_settings
from .models import EventLog, Installation, Repository


class CleanupEventsForm(forms.Form):
    """Form for the cleanup events confirmation view."""
    days_to_keep = forms.IntegerField(
        initial=app_settings.DAYS_TO_KEEP_EVENTS,
        min_value=1,
        label="Days to keep",
        help_text="Events older than this many days will be permanently deleted.",
    )


@admin.register(EventLog)
class EventLogModelAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "action", "received_at"]
    readonly_fields = ["event", "payload", "received_at"]
    actions = ["cleanup_events_action"]
    
    def get_urls(self):
        """Add the cleanup confirmation URL to the admin."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "cleanup-events/",
                self.admin_site.admin_view(self.cleanup_events_view),
                name="django_github_app_eventlog_cleanup",
            ),
        ]
        return custom_urls + urls
    
    def cleanup_events_action(self, request: HttpRequest, queryset) -> None:
        """Admin action to clean up old EventLog records."""
        # Ignore the queryset since we're cleaning up based on age
        url = reverse("admin:django_github_app_eventlog_cleanup")
        return HttpResponseRedirect(url)
    
    cleanup_events_action.short_description = "Clean up old events"
    
    def cleanup_events_view(self, request: HttpRequest):
        """View for confirming and executing the cleanup action."""
        # Get count of events that would be deleted with current settings
        cutoff_date = timezone.now() - timezone.timedelta(days=app_settings.DAYS_TO_KEEP_EVENTS)
        events_to_delete_count = EventLog.objects.filter(received_at__lte=cutoff_date).count()
        
        # Handle form submission
        if request.method == "POST":
            form = CleanupEventsForm(request.POST)
            if form.is_valid():
                days_to_keep = form.cleaned_data["days_to_keep"]
                
                # Execute the cleanup based on webhook type setting
                if app_settings.WEBHOOK_TYPE == "async":
                    # For async environments, run the async method through sync_to_async
                    deleted_count = async_to_sync(EventLog.objects.acleanup_events)(days_to_keep)
                else:
                    # For sync environments, run the sync method directly
                    deleted_count = EventLog.objects.cleanup_events(days_to_keep)
                
                self.message_user(
                    request, 
                    f"Successfully deleted {deleted_count[0]} events older than {days_to_keep} days.",
                    messages.SUCCESS
                )
                return HttpResponseRedirect(reverse("admin:django_github_app_eventlog_changelist"))
        else:
            form = CleanupEventsForm()
        
        # Render confirmation template
        context = {
            "title": "Clean up old events",
            "form": form,
            "events_to_delete_count": events_to_delete_count,
            "days_to_keep": app_settings.DAYS_TO_KEEP_EVENTS,
            "opts": self.model._meta,
        }
        return render(request, "admin/django_github_app/eventlog/cleanup_confirm.html", context)
```

We also need to create a template file at `templates/admin/django_github_app/eventlog/cleanup_confirm.html`:

```html
{% extends "admin/base_site.html" %}
{% load i18n admin_urls %}

{% block breadcrumbs %}
<div class="breadcrumbs">
  <a href="{% url 'admin:index' %}">{% translate 'Home' %}</a>
  &rsaquo; <a href="{% url 'admin:app_list' app_label=opts.app_label %}">{{ opts.app_config.verbose_name }}</a>
  &rsaquo; <a href="{% url 'admin:django_github_app_eventlog_changelist' %}">{{ opts.verbose_name_plural|capfirst }}</a>
  &rsaquo; {% translate 'Clean up old events' %}
</div>
{% endblock %}

{% block content %}
<div id="content-main">
  <div class="module">
    <h2>{% translate 'Clean up old events' %}</h2>
    <p>
      You are about to delete <strong>{{ events_to_delete_count }}</strong> events 
      that are older than {{ days_to_keep }} days.
    </p>
    <p>
      This action cannot be undone. Please confirm the number of days to keep events:
    </p>
    <form method="post">
      {% csrf_token %}
      {{ form.as_p }}
      <div class="submit-row">
        <input type="submit" class="default" value="{% translate 'Confirm deletion' %}">
        <a href="{% url 'admin:django_github_app_eventlog_changelist' %}" class="button cancel-link">{% translate 'Cancel' %}</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

## 4. Async/Sync Implementation

The implementation above handles both async and sync Django environments:

- It detects the `WEBHOOK_TYPE` setting and calls the appropriate method (`acleanup_events` for async, `cleanup_events` for sync).
- For async environments, it uses `async_to_sync` from `asgiref.sync` to call the async method from the synchronous admin view. This approach is needed because Django's admin views are synchronous even in ASGI projects.
- The code respects and uses the existing `acleanup_events`/`cleanup_events` methods, which already have proper implementations for both async and sync contexts.

## 5. Considerations and Future Improvements

- **User Experience:** The confirmation page provides transparency about how many events will be deleted and allows administrators to adjust the threshold.
- **Feedback:** Clear success messages with deletion counts provide feedback on the action's result.
- **Performance:** For very large EventLog tables, the deletion operation could be time-consuming. In a future enhancement, we might consider:
  - Running the cleanup as a background task (e.g., using Celery or Django-Q) to avoid blocking the admin interface.
  - Adding a progress indicator if the operation takes a significant amount of time.
- **Template Placement:** The new template file needs to be placed in the correct location according to Django's template loading order. We might need to ensure the library's templates are discoverable.
- **Future Archiving:** When implementing the archiving feature (issue #17), we could add a similar "Archive Events" action that moves events to storage rather than deleting them. The UI could provide options for both actions.
- **Admin Permissions:** We should ensure that this action is only available to users with appropriate permissions (delete permission on the EventLog model).

# Plan for Issue #17: Add ability to archive `EventLog` instances

## 1. Summary

Issue #17 seeks to enhance the `EventLog` model by adding the ability to archive webhook events instead of simply deleting them when they reach a certain age. This would allow users to maintain a historical record of events for auditing, debugging, or compliance purposes while still keeping the active database table lean and performant.

Currently, the only option for managing old events is to delete them through the `acleanup_events`/`cleanup_events` manager methods. The issue suggests archiving events to external storage (like S3) or a separate storage backend defined by Django's storage system.

This feature would complement the deletion functionality discussed in issue #22, giving administrators more options for managing webhook event data.

## 2. Proposed Solution

We will implement an archiving system for `EventLog` instances that will:

1. Add new methods to the `EventLogManager` for archiving events: `aarchive_events`/`archive_events`
2. Support configurable storage backends through Django's file storage system
3. Allow archiving events based on age (similar to deletion)
4. Provide ability to archive events to JSON files that can be stored in any Django-supported storage
5. Support both async and sync Django environments
6. Integrate with the admin interface to allow manual triggering of archiving

The solution will leverage Django's storage system, which provides a unified API for various storage backends (local filesystem, Amazon S3, etc.) and allows users to configure where archived events are stored based on their needs.

## 3. Code Changes Needed

### 3.1 Update `conf.py` to add new settings

```python
# Add to the default GITHUB_APP settings in conf.py
"ARCHIVE_STORAGE": None,  # Default storage backend if not specified
"ARCHIVE_LOCATION": "github_events",  # Subfolder/prefix for archived files
"ARCHIVE_FILENAME_TEMPLATE": "events_{date}_{id}.json",  # Template for archive filenames
```

### 3.2 Update `models.py` to add archiving functionality

```python
import json
import datetime
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage, Storage
from django.db import models
from django.utils import timezone

from .conf import app_settings

class EventLogManager(models.Manager["EventLog"]):
    # Existing methods...
    
    async def aarchive_events(
        self,
        days_to_keep: int = app_settings.DAYS_TO_KEEP_EVENTS,
        storage: Optional[Storage] = None,
        location: Optional[str] = None,
        delete_after_archive: bool = True,
    ) -> Tuple[int, List[str]]:
        """
        Archive events older than the specified number of days.
        
        Args:
            days_to_keep: Events older than this many days will be archived
            storage: Django storage backend to use (defaults to ARCHIVE_STORAGE or default_storage)
            location: Path/prefix within storage where archives are stored
            delete_after_archive: Whether to delete events after successful archiving
            
        Returns:
            Tuple of (number of events archived, list of archive file paths)
        """
        # Use configured storage or fall back to default
        storage = storage or app_settings.ARCHIVE_STORAGE or default_storage
        location = location or app_settings.ARCHIVE_LOCATION
        
        # Get events to archive
        cutoff_date = timezone.now() - datetime.timedelta(days=days_to_keep)
        events_to_archive = await self.filter(received_at__lte=cutoff_date)
        
        # Group events by day for more manageable archive files
        events_by_day = {}
        for event in events_to_archive:
            day_str = event.received_at.strftime("%Y-%m-%d")
            if day_str not in events_by_day:
                events_by_day[day_str] = []
            events_by_day[day_str].append(event)
        
        archive_files = []
        archived_ids = []
        
        # Create archive files
        for day_str, events in events_by_day.items():
            # Create JSON serializable data
            events_data = []
            for event in events:
                events_data.append({
                    "id": event.id,
                    "event": event.event,
                    "payload": event.payload,
                    "received_at": event.received_at.isoformat(),
                })
                archived_ids.append(event.id)
            
            # Generate archive filename
            filename = app_settings.ARCHIVE_FILENAME_TEMPLATE.format(
                date=day_str,
                id=uuid.uuid4().hex[:8],
            )
            if location:
                filename = f"{location}/{filename}"
            
            # Write JSON to storage
            content = json.dumps(events_data, indent=2)
            stored_path = await self._async_save_to_storage(
                storage, filename, content
            )
            archive_files.append(stored_path)
        
        # Delete archived events if requested
        if delete_after_archive and archived_ids:
            await self.filter(id__in=archived_ids).adelete()
        
        return len(archived_ids), archive_files
    
    @staticmethod
    async def _async_save_to_storage(
        storage: Storage, filename: str, content: str
    ) -> str:
        """Helper to save content to storage asynchronously"""
        # Most storage backends aren't async-aware, so we need to handle this
        # This approach could be optimized further based on specifics of async storage
        content_file = ContentFile(content.encode("utf-8"))
        return storage.save(filename, content_file)
    
    # Sync version of the archive method
    archive_events = async_to_sync_method(aarchive_events)
```

### 3.3 Update `admin.py` to add archive action to the admin interface

```python
# Add this to the imports
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.core.files.storage import default_storage
from asgiref.sync import async_to_sync, sync_to_async

# Add a new form for archive settings
class ArchiveEventsForm(forms.Form):
    """Form for the archive events confirmation view."""
    days_to_keep = forms.IntegerField(
        initial=app_settings.DAYS_TO_KEEP_EVENTS,
        min_value=1,
        label="Days to keep",
        help_text="Events older than this many days will be archived.",
    )
    delete_after_archive = forms.BooleanField(
        initial=True,
        required=False,
        label="Delete after archive",
        help_text="Delete events from the database after they have been archived.",
    )

# Update the EventLogModelAdmin
@admin.register(EventLog)
class EventLogModelAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "action", "received_at"]
    readonly_fields = ["event", "payload", "received_at"]
    actions = ["cleanup_events_action", "archive_events_action"]
    
    def get_urls(self):
        """Add custom URLs to the admin."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "cleanup-events/",
                self.admin_site.admin_view(self.cleanup_events_view),
                name="django_github_app_eventlog_cleanup",
            ),
            path(
                "archive-events/",
                self.admin_site.admin_view(self.archive_events_view),
                name="django_github_app_eventlog_archive",
            ),
        ]
        return custom_urls + urls
    
    # Keep existing cleanup methods...
    
    def archive_events_action(self, request: HttpRequest, queryset) -> None:
        """Admin action to archive old EventLog records."""
        # Ignore the queryset since we're archiving based on age
        url = reverse("admin:django_github_app_eventlog_archive")
        return HttpResponseRedirect(url)
    
    archive_events_action.short_description = "Archive old events"
    
    def archive_events_view(self, request: HttpRequest):
        """View for confirming and executing the archive action."""
        # Get count of events that would be archived with current settings
        cutoff_date = timezone.now() - timezone.timedelta(days=app_settings.DAYS_TO_KEEP_EVENTS)
        events_to_archive_count = EventLog.objects.filter(received_at__lte=cutoff_date).count()
        
        # Handle form submission
        if request.method == "POST":
            form = ArchiveEventsForm(request.POST)
            if form.is_valid():
                days_to_keep = form.cleaned_data["days_to_keep"]
                delete_after = form.cleaned_data["delete_after_archive"]
                
                # Execute the archive based on webhook type setting
                if app_settings.WEBHOOK_TYPE == "async":
                    archived_count, files = async_to_sync(EventLog.objects.aarchive_events)(
                        days_to_keep=days_to_keep,
                        delete_after_archive=delete_after,
                    )
                else:
                    archived_count, files = EventLog.objects.archive_events(
                        days_to_keep=days_to_keep,
                        delete_after_archive=delete_after,
                    )
                
                action = "archived and deleted" if delete_after else "archived"
                self.message_user(
                    request, 
                    f"Successfully {action} {archived_count} events older than {days_to_keep} days.",
                    messages.SUCCESS
                )
                return HttpResponseRedirect(reverse("admin:django_github_app_eventlog_changelist"))
        else:
            form = ArchiveEventsForm()
        
        # Render confirmation template
        context = {
            "title": "Archive old events",
            "form": form,
            "events_to_archive_count": events_to_archive_count,
            "days_to_keep": app_settings.DAYS_TO_KEEP_EVENTS,
            "storage_name": app_settings.ARCHIVE_STORAGE.__class__.__name__ 
                if app_settings.ARCHIVE_STORAGE else default_storage.__class__.__name__,
            "opts": self.model._meta,
        }
        return render(request, "admin/django_github_app/eventlog/archive_confirm.html", context)
```

### 3.4 Create a template file for the archive confirmation page

```html
{% extends "admin/base_site.html" %}
{% load i18n admin_urls %}

{% block breadcrumbs %}
<div class="breadcrumbs">
  <a href="{% url 'admin:index' %}">{% translate 'Home' %}</a>
  &rsaquo; <a href="{% url 'admin:app_list' app_label=opts.app_label %}">{{ opts.app_config.verbose_name }}</a>
  &rsaquo; <a href="{% url 'admin:django_github_app_eventlog_changelist' %}">{{ opts.verbose_name_plural|capfirst }}</a>
  &rsaquo; {% translate 'Archive old events' %}
</div>
{% endblock %}

{% block content %}
<div id="content-main">
  <div class="module">
    <h2>{% translate 'Archive old events' %}</h2>
    <p>
      You are about to archive <strong>{{ events_to_archive_count }}</strong> events 
      that are older than {{ days_to_keep }} days to <strong>{{ storage_name }}</strong>.
    </p>
    <p>
      Please confirm your archiving preferences:
    </p>
    <form method="post">
      {% csrf_token %}
      {{ form.as_p }}
      <div class="submit-row">
        <input type="submit" class="default" value="{% translate 'Confirm archiving' %}">
        <a href="{% url 'admin:django_github_app_eventlog_changelist' %}" class="button cancel-link">{% translate 'Cancel' %}</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

## 4. Async/Sync Implementation

The solution ensures compatibility with both async and sync Django environments:

- Both `aarchive_events` (async) and `archive_events` (sync) methods are provided
- The admin interface detects `WEBHOOK_TYPE` to use the appropriate method
- For async environments, `async_to_sync` is used since Django admin is synchronous
- The `_async_save_to_storage` method handles storage operations that may not be async-aware

## 5. Considerations and Future Improvements

- **Storage Configuration:** The solution allows users to configure any Django-compatible storage backend, making it flexible for different deployment scenarios.
- **File Format:** Events are stored as JSON files grouped by day, which balances between granularity and manageability. Alternative formats could be considered (e.g., CSV or line-delimited JSON for larger datasets).
- **Integration with S3:** For AWS S3 storage, explicit documentation would be valuable as it's likely a common use case. The solution should work with django-storages' S3 backend.
- **Performance:** For large numbers of events, the archiving process may be time-consuming. In the future, we could:
  - Add background task support (e.g., using Celery)
  - Implement batching for better memory usage
  - Add progress reporting for long-running archive operations
- **Retrieval:** Currently, archiving is a one-way process with no built-in retrieval mechanism. Future enhancements could include:
  - Search interface for archived events
  - Ability to restore archived events back to the database
  - API endpoints for accessing archived events
- **Security:** The solution should ensure that archived files inherit appropriate permissions. Storage backends typically have different permission mechanisms.
- **File Size Management:** For very large event logs, consider implementing chunking strategies to avoid creating excessively large archive files.
- **Expiry Settings:** We could add configurable retention settings for archived files (e.g., automatic deletion after X years).

# Plan for Issue #15: Allow for defining command callbacks, for issue/PR comments containing @ the github app

## 1. Summary

Issue #15 proposes adding the ability to handle command callbacks triggered by @ mentions in GitHub issue or PR comments. This feature would allow developers to create interactive GitHub Apps that can respond to user commands, similar to how Dependabot responds to commands like `@dependabot rebuild`.

The goal is to extend the existing event routing system to enable registering command handlers that will be triggered when a GitHub App is mentioned with a specific command in issue or PR comments. This would provide a natural and user-friendly way for users to interact with GitHub Apps directly from GitHub's interface.

## 2. Proposed Solution

We will extend the `GitHubRouter` class to add a new registration method called `command` that will work similarly to the existing `event` method, but specifically for handling command mentions in comments. The solution will:

1. Add a new decorator method (`command`) to the `GitHubRouter` class for registering command callbacks
2. Create new handler functions that detect @ mentions with commands in issue and PR comments
3. Extract the command and its context and pass it to the appropriate registered callback
4. Support both async and sync environments
5. Allow scoping commands to either issues, PRs, or both

This approach leverages the existing event handling infrastructure and extends it to support this new command pattern.

## 3. Code Changes Needed

### 3.1 Update `routing.py` to add command callback registration

```python
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, ClassVar, Dict, List, Literal, Optional, TypeVar, Union

from django.utils.functional import classproperty
from gidgethub import sansio
from gidgethub.routing import Router as GidgetHubRouter

from ._typing import override

AsyncCallback = Callable[..., Awaitable[None]]
SyncCallback = Callable[..., None]
CommandCallback = Callable[..., Any]  # Could be sync or async
CommandScope = Literal["issue", "pr", "both"]

CB = TypeVar("CB", AsyncCallback, SyncCallback)
CMD = TypeVar("CMD", bound=CommandCallback)


class GitHubRouter(GidgetHubRouter):
    _routers: ClassVar[List[GidgetHubRouter]] = []
    _commands: ClassVar[Dict[str, List[Dict[str, Any]]]] = {}
    
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        GitHubRouter._routers.append(self)
    
    @classproperty
    def routers(cls) -> List[GidgetHubRouter]:
        return list(cls._routers)
    
    def event(self, event_type: str, **kwargs: Any) -> Callable[[CB], CB]:
        def decorator(func: CB) -> CB:
            self.add(func, event_type, **kwargs)  # type: ignore[arg-type]
            return func
        return decorator
    
    def command(
        self, 
        cmd_name: str, 
        scope: CommandScope = "both",
        **kwargs: Any
    ) -> Callable[[CMD], CMD]:
        """
        Register a callback for handling commands in issue/PR comments.
        
        Args:
            cmd_name: The command name that triggers this callback (e.g., "rebuild" for "@app rebuild")
            scope: Where this command is valid - "issue", "pr", or "both"
            **kwargs: Additional parameters to pass to the router
            
        The callback will receive:
            event: The original issue_comment event
            gh: The GitHub API client
            cmd_args: Any arguments following the command (as a string)
            context: Dict with 'scope' (issue/pr), 'number', 'repo', and other contextual info
        """
        def decorator(func: CMD) -> CMD:
            if cmd_name not in self._commands:
                self._commands[cmd_name] = []
            
            self._commands[cmd_name].append({
                "callback": func,
                "scope": scope,
                "router": self,
                **kwargs
            })
            
            # Also register for issue_comment.created events
            if hasattr(func, "__awaitable__") or getattr(func, "__code__").co_flags & 0x80:
                # For async functions
                self._register_async_command_detector()
            else:
                # For sync functions
                self._register_sync_command_detector()
                
            return func
        return decorator
    
    def _register_async_command_detector(self) -> None:
        """Register the async detector for command mentions if not already registered."""
        # Only register once across all routers
        if not hasattr(GitHubRouter, "_async_detector_registered"):
            @self.event("issue_comment", action="created")
            async def async_command_detector(event: sansio.Event, gh: Any, *args: Any, **kwargs: Any) -> None:
                """Detect commands in comments and route to appropriate handlers."""
                comment = event.data["comment"]["body"]
                repo = event.data["repository"]["full_name"]
                app_name = None
                
                # Determine the app name - try several sources
                if "installation" in event.data:
                    # Try to get from installation data
                    app_name = event.data["installation"].get("app_slug")
                
                if not app_name:
                    # Fall back to settings
                    from .conf import app_settings
                    app_name = app_settings.SLUG
                
                # Determine if this is an issue or PR comment
                is_pr = "pull_request" in event.data["issue"]
                scope = "pr" if is_pr else "issue"
                issue_number = event.data["issue"]["number"]
                
                # Extract commands directed at this app
                pattern = rf"@{app_name}\s+(\w+)(?:\s+(.*))?$"
                for line in comment.split("\n"):
                    match = re.search(pattern, line.strip())
                    if match:
                        cmd = match.group(1).lower()
                        args = match.group(2) if match.group(2) else ""
                        
                        # Build context object
                        context = {
                            "scope": scope,
                            "number": issue_number,
                            "repo": repo,
                            "comment_id": event.data["comment"]["id"],
                            "sender": event.data["sender"]["login"],
                            "issue_url": event.data["issue"]["url"],
                            "comment_url": event.data["comment"]["url"],
                        }
                        
                        # Find registered handlers for this command
                        if cmd in self._commands:
                            for handler in self._commands[cmd]:
                                # Check if this handler applies to this scope
                                handler_scope = handler["scope"]
                                if handler_scope == "both" or handler_scope == scope:
                                    callback = handler["callback"]
                                    if hasattr(callback, "__awaitable__") or getattr(callback, "__code__").co_flags & 0x80:
                                        # Async callback
                                        await callback(event, gh, cmd_args=args, context=context, *args, **kwargs)
            
            # Mark as registered to avoid duplicate registrations
            GitHubRouter._async_detector_registered = True
    
    def _register_sync_command_detector(self) -> None:
        """Register the sync detector for command mentions if not already registered."""
        # Only register once across all routers
        if not hasattr(GitHubRouter, "_sync_detector_registered"):
            @self.event("issue_comment", action="created")
            def sync_command_detector(event: sansio.Event, gh: Any, *args: Any, **kwargs: Any) -> None:
                """Detect commands in comments and route to appropriate handlers."""
                comment = event.data["comment"]["body"]
                repo = event.data["repository"]["full_name"]
                app_name = None
                
                # Determine the app name - try several sources
                if "installation" in event.data:
                    # Try to get from installation data
                    app_name = event.data["installation"].get("app_slug")
                
                if not app_name:
                    # Fall back to settings
                    from .conf import app_settings
                    app_name = app_settings.SLUG
                
                # Determine if this is an issue or PR comment
                is_pr = "pull_request" in event.data["issue"]
                scope = "pr" if is_pr else "issue"
                issue_number = event.data["issue"]["number"]
                
                # Extract commands directed at this app
                pattern = rf"@{app_name}\s+(\w+)(?:\s+(.*))?$"
                for line in comment.split("\n"):
                    match = re.search(pattern, line.strip())
                    if match:
                        cmd = match.group(1).lower()
                        args = match.group(2) if match.group(2) else ""
                        
                        # Build context object
                        context = {
                            "scope": scope,
                            "number": issue_number,
                            "repo": repo,
                            "comment_id": event.data["comment"]["id"],
                            "sender": event.data["sender"]["login"],
                            "issue_url": event.data["issue"]["url"],
                            "comment_url": event.data["comment"]["url"],
                        }
                        
                        # Find registered handlers for this command
                        if cmd in self._commands:
                            for handler in self._commands[cmd]:
                                # Check if this handler applies to this scope
                                handler_scope = handler["scope"]
                                if handler_scope == "both" or handler_scope == scope:
                                    callback = handler["callback"]
                                    if not (hasattr(callback, "__awaitable__") or getattr(callback, "__code__").co_flags & 0x80):
                                        # Sync callback
                                        callback(event, gh, cmd_args=args, context=context, *args, **kwargs)
            
            # Mark as registered to avoid duplicate registrations
            GitHubRouter._sync_detector_registered = True
    
    async def adispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:
        found_callbacks = self.fetch(event)
        for callback in found_callbacks:
            await callback(event, *args, **kwargs)

    @override
    def dispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        found_callbacks = self.fetch(event)
        for callback in found_callbacks:
            callback(event, *args, **kwargs)
```

### 3.2 Update documentation in README.md to explain command handling

```markdown
## Command Callbacks

In addition to webhook event handling, django-github-app provides a command callback system that allows your GitHub App to respond to @mentions in issue and pull request comments. This makes it easy to build interactive GitHub Apps that can perform actions in response to user commands.

### Registering Command Handlers

For ASGI projects:

```python
# your_app/events.py
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()

# Handle "recreate" command in both issues and PRs
@gh.command("recreate")
async def recreate_command(event, gh, cmd_args, context, *args, **kwargs):
    """Handle @your-app recreate command"""
    # Post a response to the comment
    issue_url = context["issue_url"]
    comment_url = f"{issue_url}/comments"
    
    await gh.post(
        comment_url,
        data={"body": f"I'll recreate that for you @{context['sender']}!"}
    )
    
    # Perform the actual recreate logic...

# Handle "update" command only in PRs
@gh.command("update", scope="pr")
async def update_pr_command(event, gh, cmd_args, context, *args, **kwargs):
    """Handle @your-app update command in PRs"""
    # Command is only triggered in PRs
    pr_number = context["number"]
    repo = context["repo"]
    
    # You might update the PR here...
    await gh.post(
        f"/repos/{repo}/issues/{pr_number}/comments",
        data={"body": f"Updating PR #{pr_number} as requested by @{context['sender']}"}
    )
```

For WSGI projects:

```python
# your_app/events.py
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()

# Handle "recreate" command in both issues and PRs
@gh.command("recreate")
def recreate_command(event, gh, cmd_args, context, *args, **kwargs):
    """Handle @your-app recreate command"""
    # Post a response to the comment
    issue_url = context["issue_url"]
    comment_url = f"{issue_url}/comments"
    
    gh.post(
        comment_url,
        data={"body": f"I'll recreate that for you @{context['sender']}!"}
    )
    
    # Perform the actual recreate logic...
```

### Command Handler Context

Each command handler receives these arguments:

- `event`: The original `issue_comment` event
- `gh`: The GitHub API client for making API calls
- `cmd_args`: Any text following the command (useful for command parameters)
- `context`: A dictionary containing:
  - `scope`: Either "issue" or "pr" depending on where the comment was made
  - `number`: The issue or PR number
  - `repo`: Repository full name (e.g., "owner/repo")
  - `comment_id`: ID of the comment containing the command
  - `sender`: Username of the person who sent the command
  - `issue_url`: URL of the issue/PR API endpoint
  - `comment_url`: URL of the comment API endpoint

### Command Scopes

Commands can be scoped to specific contexts:

- `"both"`: Default scope, command works in both issues and PRs
- `"issue"`: Command only works in issue comments
- `"pr"`: Command only works in pull request comments

```python
# PR-only command
@gh.command("rebuild", scope="pr")
async def rebuild_pr(event, gh, cmd_args, context, *args, **kwargs):
    """Handle @your-app rebuild command in PRs"""
    # Command logic here...

# Issue-only command
@gh.command("label", scope="issue")
async def add_labels(event, gh, cmd_args, context, *args, **kwargs):
    """Handle @your-app label command in issues"""
    # Command logic here...
```
```

## 4. Implementation Considerations

The implementation handles both async and sync environments by:

- Automatically detecting whether a command callback is async or sync based on its signature
- Registering the appropriate command detector based on the callback type
- Having separate internal detectors for async and sync callbacks, registered only once
- Supporting both ASGI and WSGI projects seamlessly

## 5. Additional Considerations

- **Security:** The command handler should consider the sender's permissions on the repository before executing sensitive operations. Not all commands should be available to all users.
- **Command Validation:** Commands should validate input arguments to avoid injection attacks or unintended behavior.
- **Command Feedback:** It's a good practice to have commands respond with confirmation messages to provide feedback to users.
- **Rate Limiting:** Be mindful of GitHub API rate limits when processing commands, especially for operations that require multiple API calls.
- **Performance:** Command processing happens in the webhook request lifecycle, so long-running operations should be moved to background tasks when possible.
- **Testing:** Add comprehensive tests for command handling, including:
  - Testing command parsing and routing
  - Testing scope restrictions (issues vs PRs)
  - Testing error handling for invalid commands
- **Future Extensions:**
  - Support for command aliases
  - Help command to list available commands automatically
  - Permission system to restrict commands to specific users (e.g., repository owners, collaborators)
  - Command argument parsing for more structured command inputs
