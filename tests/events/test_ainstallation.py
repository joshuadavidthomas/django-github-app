from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from model_bakery import baker

from django_github_app.events.ainstallation import acreate_installation
from django_github_app.events.ainstallation import adelete_installation
from django_github_app.events.ainstallation import async_installation_data
from django_github_app.events.ainstallation import async_installation_repositories
from django_github_app.events.ainstallation import atoggle_installation_status
from django_github_app.models import Installation
from django_github_app.models import InstallationStatus
from django_github_app.models import Repository
from tests.utils import seq

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]


@pytest.mark.parametrize("app_settings_app_id_type", [int, str])
async def test_acreate_installation(
    app_settings_app_id_type,
    installation_id,
    repository_id,
    override_app_settings,
    create_event,
):
    data = {
        "installation": {
            "id": installation_id,
            "app_id": seq.next(),
        },
        "repositories": [
            {"id": repository_id, "node_id": "node1234", "full_name": "owner/repo"}
        ],
    }
    event = create_event("installation", delivery_id="1234", **data)

    with override_app_settings(
        APP_ID=data["installation"]["app_id"]
        if isinstance(app_settings_app_id_type, int)
        else str(data["installation"]["app_id"])
    ):
        await acreate_installation(event, None)

    installation = await Installation.objects.aget(
        installation_id=data["installation"]["id"]
    )

    assert installation.data == data["installation"]


async def test_adelete_installation(ainstallation, create_event):
    data = {
        "installation": {
            "id": ainstallation.installation_id,
        }
    }
    event = create_event("installation", delivery_id="1234", **data)

    await adelete_installation(event, None)

    assert not await Installation.objects.filter(
        installation_id=data["installation"]["id"]
    ).aexists()


@pytest.mark.parametrize(
    "status,action,expected",
    [
        (InstallationStatus.ACTIVE, "suspend", InstallationStatus.INACTIVE),
        (InstallationStatus.INACTIVE, "unsuspend", InstallationStatus.ACTIVE),
    ],
)
async def test_atoggle_installation_status_suspend(
    status, action, expected, ainstallation, create_event
):
    ainstallation.status = status
    await ainstallation.asave()

    data = {
        "action": action,
        "installation": {
            "id": ainstallation.installation_id,
        },
    }
    event = create_event("installation", delivery_id="1234", **data)

    assert ainstallation.status != expected

    await atoggle_installation_status(event, None)

    await ainstallation.arefresh_from_db()
    assert ainstallation.status == expected


async def test_async_installation_data(ainstallation, create_event):
    data = {
        "installation": {
            "id": ainstallation.installation_id,
        },
    }
    event = create_event("installation", delivery_id="1234", **data)

    assert ainstallation.data != data

    await async_installation_data(event, None)

    await ainstallation.arefresh_from_db()
    assert ainstallation.data == data["installation"]


async def test_async_installation_repositories(ainstallation, create_event):
    existing_repo = await sync_to_async(baker.make)(
        "django_github_app.Repository",
        installation=ainstallation,
        repository_id=seq.next(),
    )

    data = {
        "installation": {
            "id": ainstallation.installation_id,
        },
        "repositories_removed": [
            {
                "id": existing_repo.repository_id,
            },
        ],
        "repositories_added": [
            {
                "id": seq.next(),
                "node_id": "repo1234",
                "full_name": "owner/repo",
            }
        ],
    }
    event = create_event("installation_repositories", delivery_id="1234", **data)

    assert await Repository.objects.filter(
        repository_id=data["repositories_removed"][0]["id"]
    ).aexists()
    assert not await Repository.objects.filter(
        repository_id=data["repositories_added"][0]["id"]
    ).aexists()

    await async_installation_repositories(event, None)

    assert not await Repository.objects.filter(
        repository_id=data["repositories_removed"][0]["id"]
    ).aexists()
    assert await Repository.objects.filter(
        repository_id=data["repositories_added"][0]["id"]
    ).aexists()


async def test_async_installation_repositories_creates_installation(
    create_event, override_app_settings
):
    app_id = seq.next()
    installation_id = seq.next()

    data = {
        "installation": {
            "id": installation_id,
            "app_id": app_id,
            "account": {"login": "testorg", "type": "Organization"},
        },
        "repositories_removed": [],
        "repositories_added": [
            {
                "id": seq.next(),
                "node_id": "repo1234",
                "full_name": "owner/repo",
            }
        ],
    }
    event = create_event("installation_repositories", delivery_id="1234", **data)

    assert not await Installation.objects.filter(
        installation_id=installation_id
    ).aexists()

    with override_app_settings(APP_ID=str(app_id)):
        await async_installation_repositories(event, None)

    installation = await Installation.objects.aget(installation_id=installation_id)

    assert installation.data == data["installation"]
    assert await Repository.objects.filter(
        repository_id=data["repositories_added"][0]["id"], installation=installation
    ).aexists()
