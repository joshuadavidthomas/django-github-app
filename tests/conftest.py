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

pytest_plugins = [
    "tests.plugins.django_modeladmin",
    "tests.plugins.integration",
]


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


@pytest.fixture(scope="session", autouse=True)
def register_modeladmins(test_admin_site):
    from django_github_app.admin import EventLogModelAdmin
    from django_github_app.admin import InstallationModelAdmin
    from django_github_app.admin import RepositoryModelAdmin
    from django_github_app.models import EventLog
    from django_github_app.models import Installation
    from django_github_app.models import Repository

    test_admin_site.register(EventLog, EventLogModelAdmin)
    test_admin_site.register(Installation, InstallationModelAdmin)
    test_admin_site.register(Repository, RepositoryModelAdmin)


@pytest.fixture
def installation_id():
    return seq.next()


@pytest.fixture
def repository_id():
    return seq.next()


@pytest.fixture
def get_mock_github_api():
    def _get_mock_github_api(return_data):
        mock_api = AsyncMock(spec=AsyncGitHubAPI)

        async def mock_getitem(*args, **kwargs):
            return return_data

        async def mock_getiter(*args, **kwargs):
            for data in return_data:
                yield data

        mock_api.getitem = mock_getitem
        mock_api.getiter = mock_getiter
        mock_api.__aenter__.return_value = mock_api
        mock_api.__aexit__.return_value = None

        return mock_api

    return _get_mock_github_api


@pytest.fixture
def installation(get_mock_github_api):
    installation = baker.make(
        "django_github_app.Installation", installation_id=seq.next()
    )
    mock_github_api = get_mock_github_api(
        [
            {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq.next(), "node_id": "node2", "full_name": "owner/repo2"},
        ]
    )
    mock_github_api.installation_id = installation.installation_id
    installation.get_gh_client = MagicMock(return_value=mock_github_api)
    return installation


@pytest.fixture
async def ainstallation(get_mock_github_api):
    installation = await sync_to_async(baker.make)(
        "django_github_app.Installation", installation_id=seq.next()
    )
    mock_github_api = get_mock_github_api(
        [
            {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq.next(), "node_id": "node2", "full_name": "owner/repo2"},
        ]
    )
    mock_github_api.installation_id = installation.installation_id
    installation.get_gh_client = MagicMock(return_value=mock_github_api)
    return installation


@pytest.fixture
def repository(installation, get_mock_github_api):
    repository = baker.make(
        "django_github_app.Repository",
        repository_id=seq.next(),
        full_name="owner/repo",
        installation=installation,
    )
    mock_github_api = get_mock_github_api(
        [
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
    )
    mock_github_api.installation_id = repository.installation.installation_id
    repository.get_gh_client = MagicMock(return_value=mock_github_api)
    return repository


@pytest.fixture
async def arepository(ainstallation, get_mock_github_api):
    installation = await ainstallation
    repository = await sync_to_async(baker.make)(
        "django_github_app.Repository",
        repository_id=seq.next(),
        full_name="owner/repo",
        installation=installation,
    )
    mock_github_api = get_mock_github_api(
        [
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
    )
    mock_github_api.installation_id = repository.installation.installation_id
    repository.get_gh_client = MagicMock(return_value=mock_github_api)
    return repository
