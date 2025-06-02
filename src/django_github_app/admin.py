from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path
from django.urls import reverse

from .conf import app_settings
from .models import EventLog
from .models import Installation
from .models import Repository


class EventLogCleanupForm(forms.Form):
    days_to_keep = forms.IntegerField(
        label="Days to keep events",
        min_value=0,
        initial=app_settings.DAYS_TO_KEEP_EVENTS,
        help_text="Events older than this number of days will be deleted.",
    )


@admin.register(EventLog)
class EventLogModelAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "action", "received_at"]
    readonly_fields = ["event", "payload", "received_at"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "cleanup/",
                self.admin_site.admin_view(self.cleanup_view),
                name="django_github_app_eventlog_cleanup",
            ),
        ]
        return custom_urls + urls

    def cleanup_view(self, request):
        if request.method == "POST":
            form = EventLogCleanupForm(request.POST)
            if form.is_valid():
                days_to_keep = form.cleaned_data["days_to_keep"]
                deleted_count, _ = EventLog.objects.cleanup_events(days_to_keep)
                messages.success(
                    request,
                    f"Successfully deleted {deleted_count} event(s) older than {days_to_keep} days.",
                )
                return HttpResponseRedirect(
                    reverse("admin:django_github_app_eventlog_changelist")
                )
        else:
            form = EventLogCleanupForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Clean up Events",
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/django_github_app/eventlog/cleanup.html", context)


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
