from __future__ import annotations

from django.views.generic import View

from django_github_app.apps import GitHubAppConfig
from django_github_app.views import AsyncWebhookView
from django_github_app.views import SyncWebhookView


class TestDetectWebookType:
    def test_detect_async(self, urlpatterns):
        with urlpatterns([AsyncWebhookView]):
            webhook_type = GitHubAppConfig.detect_webhook_type()

        assert webhook_type == "async"

    def test_detect_sync(self, urlpatterns):
        with urlpatterns([SyncWebhookView]):
            webhook_type = GitHubAppConfig.detect_webhook_type()

        assert webhook_type == "sync"

    def test_detect_normal_view(self, urlpatterns):
        with urlpatterns([View]):
            webhook_type = GitHubAppConfig.detect_webhook_type()

        assert webhook_type is None

    def test_detect_none(self, urlpatterns):
        with urlpatterns([]):
            webhook_type = GitHubAppConfig.detect_webhook_type()

        assert webhook_type is None
