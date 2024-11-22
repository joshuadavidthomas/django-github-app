from __future__ import annotations

import pytest

from django_github_app.apps import GitHubAppConfig


class TestGitHubAppConfig:
    @pytest.fixture
    def app(self):
        return GitHubAppConfig.create("django_github_app")

    @pytest.mark.parametrize(
        "webhook_type",
        [
            "async",
            "sync",
        ],
    )
    def test_app_ready_urls(self, webhook_type, app, override_app_settings):
        with override_app_settings(WEBHOOK_TYPE=webhook_type):
            app.ready()
