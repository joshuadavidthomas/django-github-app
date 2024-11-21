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

        try:
            webhook_type = self.detect_webhook_type()
            if webhook_type == "async":
                from .events import ahandlers  # noqa: F401
            elif webhook_type == "sync":
                from .events import handlers  # noqa: F401
        except (ImportError, ValueError):
            pass

    @classmethod
    def detect_webhook_type(cls):
        from .views import AsyncWebhookView
        from .views import get_webhook_views

        views = get_webhook_views()
        if views:
            return "async" if issubclass(views[0], AsyncWebhookView) else "sync"
        return None
