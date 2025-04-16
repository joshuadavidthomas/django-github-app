from __future__ import annotations

from django.apps import AppConfig

from ._typing import override


class GitHubAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_github_app"
    verbose_name = "GitHub App"

    @override
    def ready(self):
        # Import checks to ensure they are registered.
        from . import checks  # noqa: F401

        # Handler loading is now deferred to the view level (AsyncWebhookView/SyncWebhookView)
        # to support lazy loading and potentially mixing view types.
        # See PLAN.md for Issue #38 for details.
        pass
