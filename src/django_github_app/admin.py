from __future__ import annotations

from django.contrib import admin

from .models import EventLog
from .models import Installation
from .models import Repository


@admin.register(EventLog)
class EventLogModelAdmin(admin.ModelAdmin):
    list_display = ["id", "event", "action", "received_at"]
    readonly_fields = ["event", "payload", "received_at"]


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
