from __future__ import annotations

from gidgethub import sansio
from gidgethub.abc import GitHubAPI

from django_github_app.models import Repository
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()


@gh.event("repository", action="renamed")
def rename_repository(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    repo = Repository.objects.get_from_event(event)
    repo.full_name = event.data["repository"]["full_name"]
    repo.save()
