from __future__ import annotations

import contextlib
import logging
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from django.conf import settings
from django.test import override_settings
from django.urls import clear_url_caches
from django.urls import path
from faker import Faker
from gidgethub import sansio

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
def baker():
    from model_bakery import baker

    return baker


@pytest.fixture
def override_app_settings():
    @contextlib.contextmanager
    def _override_app_settings(**kwargs):
        with override_settings(**{GITHUB_APP_SETTINGS_NAME: {**kwargs}}):
            yield

    return _override_app_settings


@pytest.fixture
def urlpatterns():
    @contextlib.contextmanager
    def _urlpatterns(views):
        urlpatterns = [path(f"{i}/", view.as_view()) for i, view in enumerate(views)]

        clear_url_caches()

        with override_settings(
            ROOT_URLCONF=type(
                "urls",
                (),
                {"urlpatterns": urlpatterns},
            ),
        ):
            yield

        clear_url_caches()

    return _urlpatterns


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
def aget_mock_github_api():
    def _aget_mock_github_api(return_data, installation_id=12345):
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
        mock_api.installation_id = installation_id

        return mock_api

    return _aget_mock_github_api


@pytest.fixture
def get_mock_github_api():
    def _get_mock_github_api(return_data, installation_id=12345):
        # For sync tests, we still need an async mock because get_gh_client
        # always returns AsyncGitHubAPI, even when used through async_to_sync.
        # long term, we'll probably need to just duplicate the code between
        # sync and async versions instead of relying on async_to_sync/sync_to_async
        # from asgiref, so we'll keep this separate sync mock github api client
        # around so we can swap the internals out without changing tests (hopefully)
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
        mock_api.installation_id = installation_id

        return mock_api

    return _get_mock_github_api


@pytest.fixture
def installation(get_mock_github_api, baker):
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


@pytest_asyncio.fixture
async def ainstallation(aget_mock_github_api, baker):
    installation = await sync_to_async(baker.make)(
        "django_github_app.Installation", installation_id=seq.next()
    )
    mock_github_api = aget_mock_github_api(
        [
            {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq.next(), "node_id": "node2", "full_name": "owner/repo2"},
        ]
    )
    mock_github_api.installation_id = installation.installation_id
    installation.get_gh_client = MagicMock(return_value=mock_github_api)
    return installation


@pytest.fixture
def repository(installation, get_mock_github_api, baker):
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


@pytest_asyncio.fixture
async def arepository(ainstallation, aget_mock_github_api, baker):
    repository = await sync_to_async(baker.make)(
        "django_github_app.Repository",
        repository_id=seq.next(),
        full_name="owner/repo",
        installation=ainstallation,
    )
    mock_github_api = aget_mock_github_api(
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
def faker():
    return Faker()


@pytest.fixture
def create_event(faker):
    def _create_event(event_type, delivery_id=None, **data):
        if delivery_id is None:
            delivery_id = seq.next()

        # Auto-create comment field for comment events
        if (
            event_type
            in ["issue_comment", "pull_request_review_comment", "commit_comment"]
            and "comment" not in data
        ):
            data["comment"] = {"body": f"@{faker.user_name()} {faker.sentence()}"}

        # Auto-create review field for pull request review events
        if event_type == "pull_request_review" and "review" not in data:
            data["review"] = {"body": f"@{faker.user_name()} {faker.sentence()}"}

        # Add user to comment if not present
        if "comment" in data and "user" not in data["comment"]:
            data["comment"]["user"] = {"login": faker.user_name()}

        # Add user to review if not present
        if "review" in data and "user" not in data["review"]:
            data["review"]["user"] = {"login": faker.user_name()}

        if event_type == "issue_comment" and "issue" not in data:
            data["issue"] = {"number": faker.random_int(min=1, max=1000)}

        if event_type == "commit_comment" and "commit" not in data:
            data["commit"] = {"sha": faker.sha1()}

        if event_type == "pull_request_review_comment" and "pull_request" not in data:
            data["pull_request"] = {"number": faker.random_int(min=1, max=1000)}

        if "repository" not in data and event_type in [
            "issue_comment",
            "pull_request",
            "pull_request_review_comment",
            "commit_comment",
            "push",
        ]:
            data["repository"] = {
                "owner": {"login": faker.user_name()},
                "name": faker.slug(),
            }

        return sansio.Event(data=data, event=event_type, delivery_id=delivery_id)

    return _create_event
