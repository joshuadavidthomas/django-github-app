from __future__ import annotations

import warnings

from django.apps import AppConfig
from django.conf import settings

from ._typing import override


class GitHubAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_github_app"
    verbose_name = "GitHub App"

    @override
    def ready(self):
        from . import checks  # noqa: F401
        from .conf import DEPRECATED_SETTINGS
        from .conf import GITHUB_APP_SETTINGS_NAME

        user_settings = getattr(settings, GITHUB_APP_SETTINGS_NAME, {})
        for setting, message in DEPRECATED_SETTINGS.items():
            if setting in user_settings:
                warnings.warn(message, DeprecationWarning, stacklevel=1)
