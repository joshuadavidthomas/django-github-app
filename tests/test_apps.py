from __future__ import annotations

import pytest

from django_github_app.apps import GitHubAppConfig


class TestGitHubAppConfig:
    @pytest.fixture
    def app(self):
        return GitHubAppConfig.create("django_github_app")

    @pytest.mark.parametrize(
        "view_mode",
        [
            "async",
            "sync",
        ],
    )
    def test_app_ready_urls(self, view_mode, app, override_app_settings):
        with override_app_settings(VIEW_MODE=view_mode):
            app.ready()
