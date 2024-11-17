from __future__ import annotations

from typing import Literal

import pytest
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

from django_github_app.management.commands.github import import_app
from django_github_app.models import Installation
from django_github_app.models import Repository

pytestmark = pytest.mark.django_db


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="test_")

    account_name: str
    account_type: Literal["org", "user"]
    app_id: int
    client_id: str
    installation_id: int
    name: str
    private_key: SecretStr
    webhook_secret: SecretStr


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture(autouse=True)
def setup(settings, override_app_settings):
    with override_app_settings(
        APP_ID=settings.app_id,
        CLIENT_ID=settings.client_id,
        NAME=settings.name,
        PRIVATE_KEY=settings.private_key.get_secret_value(),
        WEBHOOK_SECRET=settings.webhook_secret.get_secret_value(),
    ):
        yield


def test_import_app(settings):
    import_app(
        type=settings.account_type,
        name=settings.account_name,
        installation_id=int(settings.installation_id),
    )

    installation = Installation.objects.get(installation_id=settings.installation_id)

    assert installation.data
    assert (
        len(installation.get_repos())
        == Repository.objects.filter(installation=installation).count()
    )
