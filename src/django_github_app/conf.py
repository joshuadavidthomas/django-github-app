from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
        value = user_settings.get(__name, super().__getattribute__(__name))

        match __name:
            case "PRIVATE_KEY":
                return self._parse_private_key(value)
            case _:
                return value

    def _parse_private_key(self, value: Any) -> str:
        if not value:
            return ""

        if not isinstance(value, (str, Path)):
            return str(value)

        if isinstance(value, str) and value.startswith("-----BEGIN"):
            return value

        path = value if isinstance(value, Path) else Path(value)
        if path.is_file():
            return path.read_text()

        return str(value)

    @property
    def SLUG(self):
        return slugify(self.NAME)


app_settings = AppSettings()
