from __future__ import annotations

import warnings

import pytest

from django_github_app.apps import GitHubAppConfig


class TestGitHubAppConfig:
    @pytest.fixture
    def app(self):
        return GitHubAppConfig.create("django_github_app")

    def test_app_ready(self, app):
        app.ready()

    def test_webhook_type_deprecation_warning(self, app, override_app_settings):
        with override_app_settings(WEBHOOK_TYPE="async"):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                app.ready()

            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "WEBHOOK_TYPE" in str(w[0].message)

    def test_no_deprecation_warning_without_setting(self, app):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            app.ready()

        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0
