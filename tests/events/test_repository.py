from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async
from gidgethub import sansio
from model_bakery import baker

from django_github_app.events.repository import rename_repository
from django_github_app.models import Repository

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]


async def test_rename_repository(ainstallation, repository_id):
    installation = await ainstallation
    repository = await sync_to_async(baker.make)(
        "django_github_app.Repository",
        installation=installation,
        repository_id=repository_id,
        full_name="owner/old_name",
    )

    data = {
        "repository": {
            "id": repository.repository_id,
            "full_name": "owner/new_name",
        },
    }
    event = sansio.Event(data, event="repository", delivery_id="1234")

    assert not await Repository.objects.filter(
        full_name=data["repository"]["full_name"]
    ).aexists()

    await rename_repository(event, None)

    assert await Repository.objects.filter(
        full_name=data["repository"]["full_name"]
    ).aexists()
