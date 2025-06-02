from __future__ import annotations

import datetime

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path
from django.urls import reverse
from django.utils import timezone

from .conf import app_settings
from .models import EventLog
from .models import Installation
from .models import Repository


def get_cleanup_form(model_meta, model_class):
    """Create a cleanup form with model-specific help text and save method."""

    class CleanupForm(forms.Form):
        days_to_keep = forms.IntegerField(
            label="Days to keep",
            min_value=0,
            initial=app_settings.DAYS_TO_KEEP_EVENTS,
            help_text=f"{model_meta.verbose_name_plural.capitalize()} older than this number of days will be deleted.",
        )

        def get_queryset_to_delete(self):
            """Get the queryset of objects that will be deleted."""
            days_to_keep = self.cleaned_data["days_to_keep"]
            cutoff_date = timezone.now() - datetime.timedelta(days=days_to_keep)
            return model_class.objects.filter(received_at__lte=cutoff_date)

        def save(self):
            """Delete the events and return the count."""
            days_to_keep = self.cleaned_data["days_to_keep"]
            deleted_count, _ = model_class.objects.cleanup_events(days_to_keep)
            return deleted_count

    return CleanupForm


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
        CleanupForm = get_cleanup_form(self.model._meta, self.model)
        form = CleanupForm(request.POST or None)

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

        if form.is_valid():
            days_to_keep = form.cleaned_data["days_to_keep"]
            events_to_delete = form.get_queryset_to_delete()
            delete_count = events_to_delete.count()
            cutoff_date = timezone.now() - datetime.timedelta(days=days_to_keep)

            context = {
                **self.admin_site.each_context(request),
                "title": f"Confirm {self.model._meta.verbose_name} deletion",
                "days_to_keep": days_to_keep,
                "delete_count": delete_count,
                "cutoff_date": cutoff_date,
                "opts": self.model._meta,
                "object_name": self.model._meta.verbose_name,
                "model_count": [(self.model._meta.verbose_name_plural, delete_count)]
                if delete_count
                else [],
                "perms_lacking": None,
                "protected": None,
            }
            return render(
                request,
                "admin/django_github_app/eventlog/cleanup_confirmation.html",
                context,
            )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Clean up {self.model._meta.verbose_name_plural}",
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
