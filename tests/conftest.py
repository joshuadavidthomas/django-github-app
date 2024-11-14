from __future__ import annotations

import contextlib
import logging
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.test import override_settings
from model_bakery import baker

from django_github_app.conf import GITHUB_APP_SETTINGS_NAME
from django_github_app.github import AsyncGitHubAPI

from .settings import DEFAULT_SETTINGS
from .utils import seq

pytest_plugins = []


def pytest_configure(config):
    logging.disable(logging.CRITICAL)

    settings.configure(**DEFAULT_SETTINGS, **TEST_SETTINGS)


TEST_SETTINGS = {
    "MIDDLEWARE": [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
    "INSTALLED_APPS": [
        "django_github_app",
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
    ],
    "ROOT_URLCONF": "",
    "TEMPLATES": [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.debug",
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
            },
        }
    ],
}


@pytest.fixture
def override_app_settings():
    @contextlib.contextmanager
    def _override_app_settings(**kwargs):
        with override_settings(**{GITHUB_APP_SETTINGS_NAME: {**kwargs}}):
            yield

    return _override_app_settings


@pytest.fixture
def installation_id():
    return seq.next()


@pytest.fixture
def repository_id():
    return seq.next()


@pytest.fixture
def installation():
    return baker.make("django_github_app.Installation", installation_id=seq.next())


@pytest.fixture
async def ainstallation():
    return await sync_to_async(baker.make)(
        "django_github_app.Installation", installation_id=seq.next()
    )


@pytest.fixture
def mock_github_api():
    mock_api = AsyncMock(spec=AsyncGitHubAPI)

    async def mock_getiter(*args, **kwargs):
        test_issues = [
            {
                "number": 1,
                "title": "Test Issue 1",
                "state": "open",
            },
            {
                "number": 2,
                "title": "Test Issue 2",
                "state": "closed",
            },
        ]
        for issue in test_issues:
            yield issue

    mock_api.getiter = mock_getiter
    mock_api.__aenter__.return_value = mock_api
    mock_api.__aexit__.return_value = None

    return mock_api


@pytest.fixture
def repository(installation, mock_github_api):
    repository = baker.make(
        "django_github_app.Repository",
        repository_id=seq.next(),
        full_name="owner/repo",
        installation=installation,
    )

    mock_github_api.installation_id = repository.installation.installation_id

    if isinstance(repository, list):
        for repo in repository:
            repo.get_gh_client = MagicMock(mock_github_api)
    else:
        repository.get_gh_client = MagicMock(return_value=mock_github_api)

    return repository


@pytest.fixture
async def arepository(ainstallation, mock_github_api):
    installation = await ainstallation
    repository = await sync_to_async(baker.make)(
        "django_github_app.Repository",
        repository_id=seq.next(),
        full_name="owner/repo",
        installation=installation,
    )

    mock_github_api.installation_id = repository.installation.installation_id

    if isinstance(repository, list):
        for repo in repository:
            repo.get_gh_client = MagicMock(mock_github_api)
    else:
        repository.get_gh_client = MagicMock(return_value=mock_github_api)

    return repository
