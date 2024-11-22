from __future__ import annotations

from django.apps import AppConfig

from ._typing import override


class GitHubAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_github_app"
    verbose_name = "GitHub App"

    @override
    def ready(self):
        from . import checks  # noqa: F401
        from .conf import app_settings

        if app_settings.WEBHOOK_TYPE == "async":
            from .events import ahandlers  # noqa: F401
        elif app_settings.WEBHOOK_TYPE == "sync":
            from .events import handlers  # noqa: F401
