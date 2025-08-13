from __future__ import annotations

import datetime
import json
import time
from collections.abc import Iterator
from collections.abc import Sequence

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.urls import URLPattern
from django.urls import URLResolver
from django.urls import path
from django.urls import reverse
from django.utils import timezone

from ._typing import override
from .conf import app_settings
from .models import EventLog
from .models import Installation
from .models import Repository


class EventLogCleanupForm(forms.Form):
    days_to_keep = forms.IntegerField(
        label="Days to keep",
        min_value=0,
        initial=app_settings.DAYS_TO_KEEP_EVENTS,
        help_text="Event logs older than this number of days will be deleted.",
    )

    def save(self) -> int:
        """Delete the events and return the count."""
        days_to_keep = self.cleaned_data["days_to_keep"]
        deleted_count, _ = EventLog.objects.cleanup_events(days_to_keep)
        return deleted_count

    @property
    def to_delete_count(self) -> int:
        if not hasattr(self, "cleaned_data"):  # pragma: no cover
            raise ValidationError(
                "Form must be validated before accessing to_delete_count"
            )
        return EventLog.objects.filter(received_at__lte=self.cutoff_date).count()

    @property
    def cutoff_date(self) -> datetime.datetime:
        if not hasattr(self, "cleaned_data"):  # pragma: no cover
            raise ValidationError("Form must be validated before accessing cutoff_date")
        days_to_keep = self.cleaned_data["days_to_keep"]
        return timezone.now() - datetime.timedelta(days=days_to_keep)


@admin.register(EventLog)
class EventLogModelAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "action", "received_at"]
    readonly_fields = ["event", "payload", "received_at"]

    @override
    def get_urls(self) -> Sequence[URLResolver | URLPattern]:  # type: ignore[override]
        urls = super().get_urls()
        custom_urls = [
            path(
                "live-tail/",
                self.admin_site.admin_view(self.live_tail_view),
                name="django_github_app_eventlog_live_tail",
            ),
            path(
                "live-tail/stream/",
                self.admin_site.admin_view(self.live_tail_stream_view),
                name="django_github_app_eventlog_live_tail_stream",
            ),
            path(
                "cleanup/",
                self.admin_site.admin_view(self.cleanup_view),
                name="django_github_app_eventlog_cleanup",
            ),
        ]
        return custom_urls + urls

    def cleanup_view(self, request: HttpRequest) -> HttpResponse:
        form = EventLogCleanupForm(request.POST or None)

        # handle confirmation
        if request.POST.get("post") == "yes" and form.is_valid():
            deleted_count = form.save()
            days_to_keep = form.cleaned_data["days_to_keep"]
            event_text = "event" if deleted_count == 1 else "events"
            day_text = "day" if days_to_keep == 1 else "days"
            messages.success(
                request,
                f"Successfully deleted {deleted_count} {event_text} older than {days_to_keep} {day_text}.",
            )
            return HttpResponseRedirect(
                reverse("admin:django_github_app_eventlog_changelist")
            )

        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "opts": self.model._meta,
        }

        if form.is_valid():
            context["title"] = f"Confirm {self.model._meta.verbose_name} deletion"
            template = "cleanup_confirmation.html"
        else:
            context["title"] = f"Clean up {self.model._meta.verbose_name_plural}"
            template = "cleanup.html"

        return render(request, f"admin/django_github_app/eventlog/{template}", context)

    def live_tail_view(self, request: HttpRequest) -> HttpResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": "Live tail",
            "opts": self.model._meta,
        }
        return render(
            request, "admin/django_github_app/eventlog/live_tail.html", context
        )

    def live_tail_stream_view(self, request: HttpRequest) -> StreamingHttpResponse:
        def event_stream() -> Iterator[str]:
            since = timezone.now()  # Default to now

            if "since" in request.GET:
                since_param = str(request.GET["since"])
                try:
                    # Handle ISO format with Z suffix
                    if since_param.endswith("Z"):
                        since_param = since_param[:-1] + "+00:00"
                    parsed_time = datetime.datetime.fromisoformat(since_param)
                    if parsed_time.tzinfo is None:
                        since = timezone.make_aware(parsed_time)
                    else:
                        since = parsed_time
                except (ValueError, TypeError):
                    since = timezone.now()
            else:
                since = timezone.now()

            while True:
                events = EventLog.objects.filter(received_at__gt=since).order_by(
                    "received_at"
                )[:10]

                for event in events:
                    since = event.received_at  # Update cursor to this event's timestamp
                    event_data = {
                        "id": event.id,
                        "event": event.event,
                        "action": event.action,
                        "received_at": event.received_at.isoformat(),
                        "payload": event.payload,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

                if not events:
                    # Send keepalive
                    yield "data: {}\n\n"

                time.sleep(1)

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


@admin.register(Installation)
class InstallationModelAdmin(admin.ModelAdmin):
    list_display = ["installation_id", "status"]
    readonly_fields = ["installation_id", "data", "status"]


@admin.register(Repository)
class RepositoryModelAdmin(admin.ModelAdmin):
    list_display = ["repository_id", "full_name", "installation"]
    readonly_fields = [
        "installation",
        "repository_id",
        "repository_node_id",
        "full_name",
    ]
