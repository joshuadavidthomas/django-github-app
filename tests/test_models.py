from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest
from asgiref.sync import sync_to_async
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.utils import timezone
from gidgethub import sansio
from model_bakery import baker

from django_github_app.github import AsyncGitHubAPI
from django_github_app.models import EventLog
from django_github_app.models import Installation
from django_github_app.models import InstallationStatus
from django_github_app.models import Repository

from .utils import seq

pytestmark = pytest.mark.django_db


@pytest.fixture
def create_event():
    def _create_event(data, event):
        return sansio.Event(data=data, event=event, delivery_id=seq.next())

    return _create_event


@pytest.fixture
def private_key():
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return pem.decode("utf-8")


class TestEventLogManager:
    @pytest.mark.asyncio
    async def test_acreate_from_event(self, create_event):
        data = {"foo": "bar"}
        event = "baz"

        event_log = await EventLog.objects.acreate_from_event(create_event(data, event))

        assert event_log.event == event
        assert event_log.payload == data

    def test_create_from_event(self, create_event):
        data = {"foo": "bar"}
        event = "baz"

        event_log = EventLog.objects.create_from_event(create_event(data, event))

        assert event_log.event == event
        assert event_log.payload == data

    @pytest.mark.asyncio
    async def test_acleanup_events(self):
        days_to_cleanup = 7
        now = timezone.now()
        quantity = 5

        await sync_to_async(baker.make)(
            "django_github_app.EventLog",
            received_at=now - datetime.timedelta(days_to_cleanup + 1),
            _quantity=quantity,
        )

        deleted, _ = await EventLog.objects.acleanup_events(days_to_cleanup)

        assert deleted == quantity

    def test_cleanup_events(self):
        days_to_keep = 7
        now = timezone.now()
        quantity = 5

        baker.make(
            "django_github_app.EventLog",
            received_at=now - datetime.timedelta(days_to_keep + 1),
            _quantity=quantity,
        )

        deleted, _ = EventLog.objects.cleanup_events(days_to_keep)

        assert deleted == quantity


class TestEventLog:
    @pytest.mark.parametrize(
        "event,action,expected",
        [
            (None, None, "unknown"),
            ("foo", None, "foo"),
            ("foo", "bar", "foo bar"),
            (None, "bar", "unknown bar"),
        ],
    )
    def test_str(self, event, action, expected):
        event = baker.make(
            "django_github_app.EventLog", event=event, payload={"action": action}
        )

        assert str(event) == f"{event.pk} {expected}"

    @pytest.mark.parametrize(
        "payload,expected",
        [(None, None), ({"action": "foo"}, "foo")],
    )
    def test_action_property(self, payload, expected):
        event = baker.make("django_github_app.EventLog", payload=payload)

        assert event.action == expected


class TestInstallationManager:
    @pytest.mark.asyncio
    async def test_acreate_from_event(self, create_event, override_app_settings):
        repositories = [
            {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq.next(), "node_id": "node2", "full_name": "owner/repo2"},
        ]
        installation_data = {
            "id": seq.next(),
            "app_id": seq.next(),
        }
        event = create_event(
            {
                "installation": installation_data,
                "repositories": repositories,
            },
            "installation",
        )

        with override_app_settings(APP_ID=str(installation_data["app_id"])):
            installation = await Installation.objects.acreate_from_event(event)

        assert installation.installation_id == installation_data["id"]
        assert installation.data == installation_data
        assert await Repository.objects.filter(
            installation=installation
        ).acount() == len(repositories)

    def test_create_from_event(self, create_event, override_app_settings):
        repositories = [
            {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq.next(), "node_id": "node2", "full_name": "owner/repo2"},
        ]
        installation_data = {
            "id": seq.next(),
            "app_id": seq.next(),
        }
        event = create_event(
            {
                "installation": installation_data,
                "repositories": repositories,
            },
            "installation",
        )

        with override_app_settings(APP_ID=str(installation_data["app_id"])):
            installation = Installation.objects.create_from_event(event)

        assert installation.installation_id == installation_data["id"]
        assert installation.data == installation_data
        assert Repository.objects.filter(installation=installation).count() == len(
            repositories
        )

    @pytest.mark.asyncio
    async def test_acreate_from_gh_data(self):
        installation_data = {
            "id": seq.next(),
            "app_id": seq.next(),
        }

        installation = await Installation.objects.acreate_from_gh_data(
            installation_data
        )

        assert installation.installation_id == installation_data["id"]
        assert installation.data == installation_data

    def test_create_from_gh_data(self):
        installation_data = {
            "id": seq.next(),
            "app_id": seq.next(),
        }

        installation = Installation.objects.create_from_gh_data(installation_data)

        assert installation.installation_id == installation_data["id"]
        assert installation.data == installation_data

    @pytest.mark.asyncio
    async def test_aget_from_event(self, ainstallation, create_event):
        installation = await ainstallation
        event = create_event(
            {"installation": {"id": installation.installation_id}}, "installation"
        )

        result = await Installation.objects.aget_from_event(event)

        assert result == installation

    @pytest.mark.asyncio
    async def test_aget_from_event_doesnotexist(self, installation_id, create_event):
        event = create_event({"installation": {"id": installation_id}}, "installation")

        installation = await Installation.objects.aget_from_event(event)

        assert installation is None

    def test_get_from_event(self, installation, create_event):
        event = create_event(
            {"installation": {"id": installation.installation_id}}, "installation"
        )

        result = Installation.objects.get_from_event(event)

        assert result == installation


class TestInstallationStatus:
    @pytest.mark.parametrize(
        "action,expected",
        [
            ("deleted", InstallationStatus.INACTIVE),
            ("suspend", InstallationStatus.INACTIVE),
            ("created", InstallationStatus.ACTIVE),
            ("new_permissions_accepted", InstallationStatus.ACTIVE),
            ("unsuspend", InstallationStatus.ACTIVE),
        ],
    )
    def test_from_event(self, action, expected, create_event):
        event = create_event({"action": action}, "installation")

        assert InstallationStatus.from_event(event) == expected

    def test_from_event_invalid_action(self, create_event):
        event = create_event({"action": "invalid"}, "installation")

        with pytest.raises(ValueError):
            InstallationStatus.from_event(event)


class TestInstallation:
    def test_get_gh_client(self, installation):
        client = installation.get_gh_client()

        assert isinstance(client, AsyncGitHubAPI)
        assert client.installation_id == installation.installation_id

    @pytest.mark.parametrize("account_type", ["org", "user"])
    @pytest.mark.asyncio
    async def test_arefresh_from_gh(
        self,
        account_type,
        private_key,
        ainstallation,
        get_mock_github_api,
        override_app_settings,
    ):
        installation = await ainstallation

        mock_github_api = get_mock_github_api({"foo": "bar"})
        installation.get_gh_client = MagicMock(return_value=mock_github_api)

        with override_app_settings(PRIVATE_KEY=private_key):
            await installation.arefresh_from_gh(account_type, "test")

        assert installation.data == {"foo": "bar"}

    @pytest.mark.parametrize("account_type", ["org", "user"])
    def test_refresh_from_gh(
        self,
        account_type,
        private_key,
        installation,
        get_mock_github_api,
        override_app_settings,
    ):
        mock_github_api = get_mock_github_api({"foo": "bar"})
        installation.get_gh_client = MagicMock(return_value=mock_github_api)

        with override_app_settings(PRIVATE_KEY=private_key):
            installation.refresh_from_gh(account_type, "test")

        assert installation.data == {"foo": "bar"}

    def test_refresh_from_gh_invalid_account_type(self, installation):
        with pytest.raises(ValueError):
            installation.refresh_from_gh("invalid", "test")

    @pytest.mark.asyncio
    async def test_aget_repos(self, ainstallation):
        installation = await ainstallation

        repos = await installation.aget_repos()

        assert len(repos) == 2
        assert repos[0]["node_id"] == "node1"
        assert repos[0]["full_name"] == "owner/repo1"
        assert repos[1]["node_id"] == "node2"
        assert repos[1]["full_name"] == "owner/repo2"

    def test_get_repos(self, installation):
        repos = installation.get_repos()

        assert len(repos) == 2
        assert repos[0]["node_id"] == "node1"
        assert repos[0]["full_name"] == "owner/repo1"
        assert repos[1]["node_id"] == "node2"
        assert repos[1]["full_name"] == "owner/repo2"

    def test_app_slug(self):
        app_slug = "foo"
        installation = baker.make(
            "django_github_app.Installation",
            installation_id=seq.next(),
            data={"app_slug": app_slug},
        )

        assert installation.app_slug == app_slug


class TestRepositoryManager:
    @pytest.mark.asyncio
    async def test_acreate_from_gh_data_list(self, ainstallation):
        installation = await ainstallation
        data = [
            {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq.next(), "node_id": "node2", "full_name": "owner/repo2"},
        ]

        repositories = await Repository.objects.acreate_from_gh_data(data, installation)

        assert len(repositories) == len(data)
        for i, repo in enumerate(repositories):
            assert repo.repository_id == data[i]["id"]
            assert repo.repository_node_id == data[i]["node_id"]
            assert repo.full_name == data[i]["full_name"]
            assert repo.installation_id == installation.id

    def test_create_from_gh_data_list(self, installation):
        data = [
            {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq.next(), "node_id": "node2", "full_name": "owner/repo2"},
        ]

        repositories = Repository.objects.create_from_gh_data(data, installation)

        assert len(repositories) == len(data)
        for i, repo in enumerate(repositories):
            assert repo.repository_id == data[i]["id"]
            assert repo.repository_node_id == data[i]["node_id"]
            assert repo.full_name == data[i]["full_name"]
            assert repo.installation_id == installation.id

    @pytest.mark.asyncio
    async def test_acreate_from_gh_data_single(self, ainstallation):
        installation = await ainstallation
        data = {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"}

        repository = await Repository.objects.acreate_from_gh_data(data, installation)

        assert repository.repository_id == data["id"]
        assert repository.repository_node_id == data["node_id"]
        assert repository.full_name == data["full_name"]
        assert repository.installation_id == installation.id

    def test_create_from_gh_data_single(self, installation):
        data = {"id": seq.next(), "node_id": "node1", "full_name": "owner/repo1"}

        repository = Repository.objects.create_from_gh_data(data, installation)

        assert repository.repository_id == data["id"]
        assert repository.repository_node_id == data["node_id"]
        assert repository.full_name == data["full_name"]
        assert repository.installation_id == installation.id

    @pytest.mark.asyncio
    async def test_aget_from_event(self, arepository, create_event):
        repository = await arepository

        data = {
            "repository": {
                "id": repository.repository_id,
                "node_id": repository.repository_node_id,
                "full_name": repository.full_name,
            }
        }

        repo = await Repository.objects.aget_from_event(
            create_event(data, "repository")
        )

        assert repo.repository_id == data["repository"]["id"]
        assert repo.repository_node_id == data["repository"]["node_id"]
        assert repo.full_name == data["repository"]["full_name"]
        assert repo.installation_id == repository.installation.id

    @pytest.mark.asyncio
    async def test_aget_from_event_doesnotexist(self, repository_id, create_event):
        data = {
            "repository": {
                "id": repository_id,
            }
        }

        repo = await Repository.objects.aget_from_event(
            create_event(data, "repository")
        )

        assert repo is None

    def test_get_from_event(self, repository, create_event):
        data = {
            "repository": {
                "id": repository.repository_id,
                "node_id": repository.repository_node_id,
                "full_name": repository.full_name,
            }
        }

        repo = Repository.objects.get_from_event(create_event(data, "repository"))

        assert repo.repository_id == data["repository"]["id"]
        assert repo.repository_node_id == data["repository"]["node_id"]
        assert repo.full_name == data["repository"]["full_name"]
        assert repo.installation_id == repository.installation.id


class TestRepository:
    def test_get_gh_client(self, repository):
        client = repository.get_gh_client()

        assert isinstance(client, AsyncGitHubAPI)
        assert client.installation_id == repository.installation.installation_id

    @pytest.mark.asyncio
    async def test_aget_issues(self, arepository):
        repository = await arepository

        issues = await repository.aget_issues()

        assert len(issues) == 2
        assert issues[0]["number"] == 1
        assert issues[0]["title"] == "Test Issue 1"
        assert issues[1]["number"] == 2
        assert issues[1]["title"] == "Test Issue 2"

    def test_get_issues(self, repository):
        issues = repository.get_issues()

        assert len(issues) == 2
        assert issues[0]["number"] == 1
        assert issues[0]["title"] == "Test Issue 1"
        assert issues[1]["number"] == 2
        assert issues[1]["title"] == "Test Issue 2"
