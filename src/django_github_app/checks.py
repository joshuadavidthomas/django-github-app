from __future__ import annotations

from django.core.checks import Error
from django.core.checks import Tags
from django.core.checks import register

from django_github_app.views import AsyncWebhookView
from django_github_app.views import get_webhook_views


@register(Tags.urls)
def check_webhook_views(app_configs, **kwargs):
    errors = []
    views = get_webhook_views()

    if views:
        view_types = {
            "async" if issubclass(v, AsyncWebhookView) else "sync" for v in views
        }
        if len(view_types) > 1:
            errors.append(
                Error(
                    "Multiple webhook view types detected.",
                    hint="Use either AsyncWebhookView or SyncWebhookView, not both.",
                    obj="django_github_app.views",
                    id="django_github_app.E001",
                )
            )

    return errors
