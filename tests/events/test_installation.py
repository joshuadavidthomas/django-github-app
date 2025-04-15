from __future__ import annotations

import pytest
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

pytestmark = [pytest.mark.django_db]


@pytest.mark.parametrize("app_settings_app_id_type", [int, str])
def test_create_installation(
    app_settings_app_id_type, installation_id, repository_id, override_app_settings
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

    with override_app_settings(
        APP_ID=data["installation"]["app_id"]
        if isinstance(app_settings_app_id_type, int)
        else str(data["installation"]["app_id"])
    ):
        create_installation(event, None)

    installation = Installation.objects.get(installation_id=data["installation"]["id"])

    assert installation.data == data["installation"]


def test_delete_installation(installation):
    data = {
        "installation": {
            "id": installation.installation_id,
        }
    }
    event = sansio.Event(data, event="installation", delivery_id="1234")

    delete_installation(event, None)

    assert not Installation.objects.filter(
        installation_id=data["installation"]["id"]
    ).exists()


@pytest.mark.parametrize(
    "status,action,expected",
    [
        (InstallationStatus.ACTIVE, "suspend", InstallationStatus.INACTIVE),
        (InstallationStatus.INACTIVE, "unsuspend", InstallationStatus.ACTIVE),
    ],
)
def test_toggle_installation_status_suspend(status, action, expected, installation):
    installation.status = status
    installation.save()

    data = {
        "action": action,
        "installation": {
            "id": installation.installation_id,
        },
    }
    event = sansio.Event(data, event="installation", delivery_id="1234")

    assert installation.status != expected

    toggle_installation_status(event, None)

    installation.refresh_from_db()
    assert installation.status == expected


def test_sync_installation_data(installation):
    data = {
        "installation": {
            "id": installation.installation_id,
        },
    }
    event = sansio.Event(data, event="installation", delivery_id="1234")

    assert installation.data != data

    sync_installation_data(event, None)

    installation.refresh_from_db()
    assert installation.data == data["installation"]


def test_sync_installation_repositories(installation):
    existing_repo = baker.make(
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

    assert Repository.objects.filter(
        repository_id=data["repositories_removed"][0]["id"]
    ).exists()
    assert not Repository.objects.filter(
        repository_id=data["repositories_added"][0]["id"]
    ).exists()

    sync_installation_repositories(event, None)

    assert not Repository.objects.filter(
        repository_id=data["repositories_removed"][0]["id"]
    ).exists()
    assert Repository.objects.filter(
        repository_id=data["repositories_added"][0]["id"]
    ).exists()
