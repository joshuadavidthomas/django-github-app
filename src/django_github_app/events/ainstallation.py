from __future__ import annotations

from gidgethub import sansio
from gidgethub.abc import GitHubAPI

from django_github_app.models import Installation
from django_github_app.models import InstallationStatus
from django_github_app.models import Repository
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()


@gh.event("installation", action="created")
async def acreate_installation(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    await Installation.objects.acreate_from_event(event)


@gh.event("installation", action="deleted")
async def adelete_installation(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    installation = await Installation.objects.aget_from_event(event)
    await installation.adelete()


@gh.event("installation", action="suspend")
@gh.event("installation", action="unsuspend")
async def atoggle_installation_status(
    event: sansio.Event, gh: GitHubAPI, *args, **kwargs
):
    installation = await Installation.objects.aget_from_event(event)
    installation.status = InstallationStatus.from_event(event)
    await installation.asave()


@gh.event("installation", action="new_permissions_accepted")
async def async_installation_data(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    installation = await Installation.objects.aget_from_event(event)
    installation.data = event.data["installation"]
    await installation.asave()


@gh.event("installation_repositories")
async def async_installation_repositories(
    event: sansio.Event, gh: GitHubAPI, *args, **kwargs
):
    await Repository.objects.async_repositories_from_event(event)
