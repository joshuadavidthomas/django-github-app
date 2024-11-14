from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from gidgethub.abc import sansio
from model_bakery import baker

from django_github_app.events.installation import create_installation
from django_github_app.events.installation import delete_installation
from django_github_app.events.installation import sync_installation_data
from django_github_app.events.installation import sync_installation_repositories
from django_github_app.events.installation import toggle_installation_status
from django_github_app.models import Installation
from django_github_app.models import InstallationStatus
from django_github_app.models import Repository
from tests.utils import seq

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]


async def test_create_installation(
    installation_id, repository_id, override_app_settings
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
    event = sansio.Event(data, event="installation", delivery_id="1234")

    with override_app_settings(APP_ID=str(data["installation"]["app_id"])):
        await create_installation(event, None)

    installation = await Installation.objects.aget(
        installation_id=data["installation"]["id"]
    )

    assert installation.data == data["installation"]


async def test_delete_installation(ainstallation):
    installation = await ainstallation
    data = {
        "installation": {
            "id": installation.installation_id,
        }
    }
    event = sansio.Event(data, event="installation", delivery_id="1234")

    await delete_installation(event, None)

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
async def test_toggle_installation_status_suspend(
    status, action, expected, ainstallation
):
    installation = await ainstallation
    installation.status = status
    await installation.asave()

    data = {
        "action": action,
        "installation": {
            "id": installation.installation_id,
        },
    }
    event = sansio.Event(data, event="installation", delivery_id="1234")

    assert installation.status != expected

    await toggle_installation_status(event, None)

    await installation.arefresh_from_db()
    assert installation.status == expected


async def test_sync_installation_data(ainstallation):
    installation = await ainstallation

    data = {
        "installation": {
            "id": installation.installation_id,
        },
    }
    event = sansio.Event(data, event="installation", delivery_id="1234")

    assert installation.data != data

    await sync_installation_data(event, None)

    await installation.arefresh_from_db()
    assert installation.data == data["installation"]


async def test_sync_installation_repositories(ainstallation):
    installation = await ainstallation
    existing_repo = await sync_to_async(baker.make)(
        "django_github_app.Repository",
        installation=installation,
        repository_id=seq.next(),
    )

    data = {
        "installation": {
            "id": installation.installation_id,
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
    event = sansio.Event(data, event="installation", delivery_id="1234")

    assert await Repository.objects.filter(
        repository_id=data["repositories_removed"][0]["id"]
    ).aexists()
    assert not await Repository.objects.filter(
        repository_id=data["repositories_added"][0]["id"]
    ).aexists()

    await sync_installation_repositories(event, None)

    assert not await Repository.objects.filter(
        repository_id=data["repositories_removed"][0]["id"]
    ).aexists()
    assert await Repository.objects.filter(
        repository_id=data["repositories_added"][0]["id"]
    ).aexists()
