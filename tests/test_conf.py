from __future__ import annotations

import pytest
from django.conf import settings

from django_github_app.conf import GITHUB_APP_SETTINGS_NAME
from django_github_app.conf import app_settings


@pytest.mark.parametrize(
    "setting,default_setting",
    [
        ("APP_ID", ""),
        ("AUTO_CLEANUP_EVENTS", True),
        ("CLIENT_ID", ""),
        ("DAYS_TO_KEEP_EVENTS", 7),
        ("NAME", ""),
        ("PRIVATE_KEY", ""),
        ("WEBHOOK_SECRET", ""),
    ],
)
def test_default_settings(setting, default_setting):
    user_settings = getattr(settings, GITHUB_APP_SETTINGS_NAME, {})

    assert user_settings == {}
    assert getattr(app_settings, setting) == default_setting


@pytest.mark.parametrize(
    "name,expected",
    [
        ("@username - app name", "username-app-name"),
        ("@username/app-name", "usernameapp-name"),
        ("@org_name/app_v2.0", "org_nameapp_v20"),
        ("  Spaces  Everywhere  ", "spaces-everywhere"),
        ("@multiple@symbols#here", "multiplesymbolshere"),
        ("camelCaseApp", "camelcaseapp"),
        ("UPPERCASE_APP", "uppercase_app"),
        ("app.name.with.dots", "appnamewithdots"),
        ("special-&*()-chars", "special-chars"),
        ("emoji🚀app", "emojiapp"),
        ("@user/multiple/slashes/app", "usermultipleslashesapp"),
        ("", ""),  # Empty string case
        ("   ", ""),  # Whitespace only case
        ("app-name_123", "app-name_123"),
        ("v1.0.0-beta", "v100-beta"),
    ],
)
def test_slug(name, expected, override_app_settings):
    with override_app_settings(NAME=name):
        assert app_settings.SLUG == expected
