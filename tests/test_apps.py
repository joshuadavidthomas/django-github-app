from __future__ import annotations

from unittest.mock import patch

import pytest
from django.views.generic import View

from django_github_app.apps import GitHubAppConfig
from django_github_app.views import AsyncWebhookView
from django_github_app.views import SyncWebhookView


class TestGitHubAppConfig:
    @pytest.fixture
    def app(self):
        return GitHubAppConfig.create("django_github_app")

    @pytest.mark.parametrize(
        "urls",
        [
            [SyncWebhookView],
            [AsyncWebhookView],
            [View],
            [],
        ],
    )
    def test_app_ready_urls(self, urls, app, urlpatterns):
        with urlpatterns(urls):
            app.ready()

    @pytest.mark.parametrize("error", [ImportError, ValueError])
    def test_app_ready_error(self, error, app):
        with patch.object(GitHubAppConfig, "detect_webhook_type", side_effect=error):
            app.ready()

    @pytest.mark.parametrize(
        "urls, expected",
        [
            ([SyncWebhookView], "sync"),
            ([AsyncWebhookView], "async"),
            ([View], None),
            ([], None),
        ],
    )
    def test_detect_webhook_type(self, urls, expected, urlpatterns):
        with urlpatterns(urls):
            webhook_type = GitHubAppConfig.detect_webhook_type()

        assert webhook_type == expected
