from __future__ import annotations

from django_github_app.apps import GitHubAppConfig


class TestGitHubAppConfig:
    def test_app_ready(self):
        app = GitHubAppConfig.create("django_github_app")
        app.ready()
