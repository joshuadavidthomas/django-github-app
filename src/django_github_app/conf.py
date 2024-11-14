from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.utils.text import slugify

from ._typing import override

GITHUB_APP_SETTINGS_NAME = "GITHUB_APP"


@dataclass(frozen=True)
class AppSettings:
    APP_ID: str = ""
    AUTO_CLEANUP_EVENTS: bool = True
    CLIENT_ID: str = ""
    DAYS_TO_KEEP_EVENTS: int = 7
    NAME: str = ""
    PRIVATE_KEY: str = ""
    WEBHOOK_SECRET: str = ""

    @override
    def __getattribute__(self, __name: str) -> Any:
        user_settings = getattr(settings, GITHUB_APP_SETTINGS_NAME, {})
        return user_settings.get(__name, super().__getattribute__(__name))

    @property
    def SLUG(self):
        return slugify(self.NAME)


app_settings = AppSettings()
