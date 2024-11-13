from __future__ import annotations

import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from asgiref.sync import sync_to_async
from django.test import override_settings
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
        return sansio.Event(data=data, event=event, delivery_id=seq("delivery-"))

    return _create_event


@pytest.fixture
def create_installation(installation_id):
    def _create_installation(**kwargs):
        return baker.make(
            "django_github_app.Installation",
            installation_id=kwargs.pop("installation_id", installation_id),
            **kwargs,
        )

    return _create_installation


@pytest.fixture
def acreate_installation(installation_id):
    async def _acreate_installation(**kwargs):
        return await sync_to_async(baker.make)(
            "django_github_app.Installation",
            installation_id=kwargs.pop("installation_id", installation_id),
            **kwargs,
        )

    return _acreate_installation


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
def create_repository(installation, mock_github_api, repository_id):
    def _create_repository(**kwargs):
        repository = baker.make(
            "django_github_app.Repository",
            repository_id=repository_id,
            full_name=kwargs.pop("full_name", "owner/repo"),
            installation=kwargs.pop("installation", installation),
            **kwargs,
        )

        mock_github_api.installation_id = repository.installation.installation_id

        if isinstance(repository, list):
            for repo in repository:
                repo.get_gh_client = MagicMock(mock_github_api)
        else:
            repository.get_gh_client = MagicMock(return_value=mock_github_api)
        return repository

    return _create_repository


@pytest.fixture
def acreate_repository(ainstallation, mock_github_api, repository_id):
    async def _acreate_repository(**kwargs):
        repository = await sync_to_async(baker.make)(
            "django_github_app.Repository",
            repository_id=repository_id,
            full_name=kwargs.pop("full_name", "owner/repo"),
            installation=kwargs.pop("installation", await ainstallation),
            **kwargs,
        )

        mock_github_api.installation_id = repository.installation.installation_id

        if isinstance(repository, list):
            for repo in repository:
                repo.get_gh_client = MagicMock(mock_github_api)
        else:
            repository.get_gh_client = MagicMock(return_value=mock_github_api)

        return repository

    return _acreate_repository


@pytest.fixture
def repository(create_repository):
    return create_repository()


@pytest.fixture
async def arepository(acreate_repository):
    return await acreate_repository()


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
    async def test_acreate_from_event(self, create_event):
        repositories = [
            {"id": seq(1000), "node_id": "node1", "full_name": "owner/repo1"},
            {"id": seq(1000), "node_id": "node2", "full_name": "owner/repo2"},
        ]
        installation_data = {
            "id": seq(1000),
            "app_id": seq(1000),
        }
        event = create_event(
            {
                "installation": installation_data,
                "repositories": repositories,
            },
            "installation",
        )

        with override_settings(
            DJANGO_GITHUB_APP={"APP_ID": str(installation_data["app_id"])}
        ):
            installation = await Installation.objects.acreate_from_event(event)

        assert installation.installation_id == installation_data["id"]
        assert installation.data == installation_data
        assert await Repository.objects.filter(
            installation=installation
        ).acount() == len(repositories)

    def test_create_from_event(self, create_event):
        repositories = [
            {"id": 1, "node_id": "node1", "full_name": "owner/repo1"},
            {"id": 2, "node_id": "node2", "full_name": "owner/repo2"},
        ]
        installation_data = {
            "id": seq(1000),
            "app_id": seq(1000),
        }
        event = create_event(
            {
                "installation": installation_data,
                "repositories": repositories,
            },
            "installation",
        )

        with override_settings(
            DJANGO_GITHUB_APP={"APP_ID": str(installation_data["app_id"])}
        ):
            installation = Installation.objects.create_from_event(event)

        assert installation.installation_id == installation_data["id"]
        assert installation.data == installation_data
        assert Repository.objects.filter(installation=installation).count() == len(
            repositories
        )

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


# class TestInstallation:
#     TEST_CASES_STATUS = [
#         (InstallationStatus.ACTIVE, "created", InstallationStatus.ACTIVE),
#         (InstallationStatus.INACTIVE, "created", InstallationStatus.ACTIVE),
#         (InstallationStatus.ACTIVE, "deleted", InstallationStatus.INACTIVE),
#         (InstallationStatus.INACTIVE, "deleted", InstallationStatus.INACTIVE),
#         (
#             InstallationStatus.ACTIVE,
#             "new_permissions_accepted",
#             InstallationStatus.ACTIVE,
#         ),
#         (
#             InstallationStatus.INACTIVE,
#             "new_permissions_accepted",
#             InstallationStatus.ACTIVE,
#         ),
#         (InstallationStatus.ACTIVE, "suspend", InstallationStatus.INACTIVE),
#         (InstallationStatus.INACTIVE, "suspend", InstallationStatus.INACTIVE),
#         (InstallationStatus.ACTIVE, "unsuspend", InstallationStatus.ACTIVE),
#         (InstallationStatus.INACTIVE, "unsuspend", InstallationStatus.ACTIVE),
#     ]
#
#     @pytest.fixture
#     def installation_event(self, create_event):
#         def _installation_event(action, installation_id):
#             return create_event(
#                 {"action": action, "installation": {"id": installation_id}},
#                 "installation",
#             )
#
#         return _installation_event
#
#     @pytest.mark.parametrize("status,action,expected", TEST_CASES_STATUS)
#     @pytest.mark.asyncio
#     async def test_atoggle_status_from_event(
#         self, status, action, expected, acreate_installation, installation_event
#     ):
#         installation = await acreate_installation(status=status)
#         event = installation_event(action, installation.installation_id)
#
#         assert installation.status == status
#
#         await installation.atoggle_status_from_event(event)
#
#         assert installation.status == expected
#
#     @pytest.mark.parametrize("status,action,expected", TEST_CASES_STATUS)
#     def test_toggle_status_from_event(
#         self, status, action, expected, create_installation, installation_event
#     ):
#         installation = create_installation(status=status)
#         event = installation_event(action, installation.installation_id)
#
#         assert installation.status == status
#
#         installation.toggle_status_from_event(event)
#
#         assert installation.status == expected
#
#     @pytest.mark.asyncio
#     async def test_async_data_from_event(self, ainstallation, create_event):
#         data = {"installation": {"foo": "bar"}}
#         event = create_event(data, "installation")
#         installation = await ainstallation
#
#         await installation.async_data_from_event(event)
#
#         assert installation.data == data["installation"]
#
#     def test_sync_data_from_event(self, installation, create_event):
#         data = {"installation": {"foo": "bar"}}
#         event = create_event(data, "installation")
#
#         installation.sync_data_from_event(event)
#
#         assert installation.data == data["installation"]
#
#     @pytest.mark.asyncio
#     async def test_async_repositories_from_event(
#         self, ainstallation, acreate_repository, create_event
#     ):
#         installation = await ainstallation
#
#         removed_repos = [
#             {
#                 "id": repo.repository_id,
#                 "node_id": repo.repository_node_id,
#                 "full_name": repo.full_name,
#             }
#             for repo in await acreate_repository(
#                 installation=installation,
#                 repository_id=itertools.cycle(seq.iter(1000)),
#                 _quantity=2,
#             )
#         ]
#         added_repos = [
#             {
#                 "id": i,
#                 "node_id": f"node{i}",
#                 "full_name": f"owner/repo{i}",
#             }
#             for i in itertools.islice(seq.iter(1000), 2)
#         ]
#
#         event = create_event(
#             {
#                 "repositories_removed": removed_repos,
#                 "repositories_added": added_repos,
#             },
#             "installation",
#         )
#
#         await installation.async_repositories_from_event(event)
#
#         remaining = await Repository.objects.filter(
#             repository_id__in=[r["id"] for r in removed_repos]
#         ).acount()
#         assert remaining == 0
#
#         new_repos = await Repository.objects.filter(
#             repository_id__in=[r["id"] for r in added_repos]
#         ).acount()
#         assert new_repos == len(added_repos)
#
#         installation_repos = await Repository.objects.filter(
#             installation=installation
#         ).acount()
#         assert installation_repos == len(added_repos)
#
#     def test_sync_repositories_from_event(
#         self, installation, create_repository, create_event
#     ):
#         removed_repos = [
#             {
#                 "id": repo.repository_id,
#                 "node_id": repo.repository_node_id,
#                 "full_name": repo.full_name,
#             }
#             for repo in create_repository(
#                 installation=installation,
#                 repository_id=itertools.cycle(seq.iter(1000)),
#                 _quantity=2,
#             )
#         ]
#         added_repos = [
#             {
#                 "id": i,
#                 "node_id": f"node{i}",
#                 "full_name": f"owner/repo{i}",
#             }
#             for i in itertools.islice(seq.iter(1000), 2)
#         ]
#
#         event = create_event(
#             {
#                 "repositories_removed": removed_repos,
#                 "repositories_added": added_repos,
#             },
#             "installation",
#         )
#
#         installation.sync_repositories_from_event(event)
#
#         remaining = Repository.objects.filter(
#             repository_id__in=[r["id"] for r in removed_repos]
#         )
#         assert remaining.count() == 0
#
#         new_repos = Repository.objects.filter(
#             repository_id__in=[r["id"] for r in added_repos]
#         ).count()
#         assert new_repos == len(added_repos)
#
#         installation_repos = Repository.objects.filter(
#             installation=installation
#         ).count()
#         assert installation_repos == len(added_repos)


class TestRepositoryManager:
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

    # @pytest.mark.asyncio
    # async def test_async_fields_from_event(self, arepository, create_event):
    #     repository = await arepository
    #     data = {
    #         "repository": {
    #             "full_name": "owner/new_name",
    #         }
    #     }
    #
    #     assert repository.full_name != data["repository"]["full_name"]
    #
    #     await repository.async_fields_from_event(
    #         create_event(data, "repository"), data["repository"].keys()
    #     )
    #
    #     assert repository.full_name == data["repository"]["full_name"]
    #
    # @pytest.mark.asyncio
    # async def test_async_fields_from_event_no_fields(self, arepository, create_event):
    #     repository = await arepository
    #     data = {
    #         "repository": {
    #             "full_name": "owner/new_name",
    #         }
    #     }
    #
    #     assert repository.full_name != data["repository"]["full_name"]
    #
    #     await repository.async_fields_from_event(create_event(data, "repository"))
    #
    #     assert repository.full_name != data["repository"]["full_name"]
    #
    # @pytest.mark.asyncio
    # async def test_async_fields_from_event_invalid_field(
    #     self, arepository, create_event
    # ):
    #     repository = await arepository
    #     data = {
    #         "repository": {
    #             "invalid_field": "foo",
    #         }
    #     }
    #
    #     with pytest.raises(ValueError):
    #         await repository.async_fields_from_event(
    #             create_event(data, "repository"), data["repository"].keys()
    #         )
    #
    # def test_sync_fields_from_event(self, repository, create_event):
    #     data = {
    #         "repository": {
    #             "full_name": "owner/new_name",
    #         }
    #     }
    #
    #     assert repository.full_name != data["repository"]["full_name"]
    #
    #     repository.sync_fields_from_event(
    #         create_event(data, "repository"), data["repository"].keys()
    #     )
    #
    #     assert repository.full_name == data["repository"]["full_name"]

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
