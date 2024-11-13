from __future__ import annotations

from django.apps import AppConfig

from ._typing import override


class GitHubAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_github_app"
    verbose_name = "GitHub App"

    @override
    def ready(self):
        from . import events  # noqa: F401
