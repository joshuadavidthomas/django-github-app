from __future__ import annotations

import pytest
from gidgethub import sansio
from model_bakery import baker

from django_github_app.events.repository import rename_repository
from django_github_app.models import Repository

pytestmark = [pytest.mark.django_db]


def test_rename_repository(installation, repository_id):
    repository = baker.make(
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

    assert not Repository.objects.filter(
        full_name=data["repository"]["full_name"]
    ).exists()

    rename_repository(event, None)

    assert Repository.objects.filter(full_name=data["repository"]["full_name"]).exists()
