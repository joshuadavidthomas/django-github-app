from __future__ import annotations

from pathlib import Path

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
    "private_key,expected",
    [
        (
            "-----BEGIN RSA PRIVATE KEY-----\nkey content\n-----END RSA PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----\nkey content\n-----END RSA PRIVATE KEY-----",
        ),
        ("/path/that/does/not/exist.pem", "/path/that/does/not/exist.pem"),
        (Path("/path/that/does/not/exist.pem"), "/path/that/does/not/exist.pem"),
        ("", ""),
        ("/path/with/BEGIN/in/it/key.pem", "/path/with/BEGIN/in/it/key.pem"),
        ("////", "////"),
        (123, "123"),
        (None, ""),
    ],
)
def test_private_key_handling(private_key, expected, override_app_settings):
    with override_app_settings(PRIVATE_KEY=private_key):
        assert app_settings.PRIVATE_KEY == expected


def test_private_key_from_file(tmp_path, override_app_settings):
    key_content = "-----BEGIN RSA PRIVATE KEY-----\ntest key content\n-----END RSA PRIVATE KEY-----"
    key_file = tmp_path / "test_key.pem"
    key_file.write_text(key_content)

    for key_path in (str(key_file), key_file):
        with override_app_settings(PRIVATE_KEY=key_path):
            assert app_settings.PRIVATE_KEY == key_content


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
        ("", ""),
        ("   ", ""),
        ("app-name_123", "app-name_123"),
        ("v1.0.0-beta", "v100-beta"),
    ],
)
def test_slug(name, expected, override_app_settings):
    with override_app_settings(NAME=name):
        assert app_settings.SLUG == expected
