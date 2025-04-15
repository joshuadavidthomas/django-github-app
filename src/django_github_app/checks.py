from __future__ import annotations

from django.core.checks import Error
from django.core.checks import Tags
from django.core.checks import register
from django.urls import get_resolver

from .views import AsyncWebhookView
from .views import SyncWebhookView


def get_webhook_views():
    resolver = get_resolver()
    found_views = []

    for pattern in resolver.url_patterns:
        if hasattr(pattern, "callback"):
            callback = pattern.callback
            view_class = getattr(callback, "view_class", None)
            if view_class:
                if issubclass(view_class, AsyncWebhookView | SyncWebhookView):
                    found_views.append(view_class)

    return found_views


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
