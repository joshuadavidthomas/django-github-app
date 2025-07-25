from __future__ import annotations

from gidgethub import sansio
from gidgethub.abc import GitHubAPI

from django_github_app.models import Installation
from django_github_app.models import InstallationStatus
from django_github_app.models import Repository
from django_github_app.routing import GitHubRouter

gh = GitHubRouter()


@gh.event("installation", action="created")
def create_installation(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    Installation.objects.create_from_event(event)


@gh.event("installation", action="deleted")
def delete_installation(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    installation = Installation.objects.get_from_event(event)
    installation.delete()


@gh.event("installation", action="suspend")
@gh.event("installation", action="unsuspend")
def toggle_installation_status(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    installation = Installation.objects.get_from_event(event)
    installation.status = InstallationStatus.from_event(event)
    installation.save()


@gh.event("installation", action="new_permissions_accepted")
def sync_installation_data(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    installation = Installation.objects.get_from_event(event)
    installation.data = event.data["installation"]
    installation.save()


@gh.event("installation_repositories")
def sync_installation_repositories(event: sansio.Event, gh: GitHubAPI, *args, **kwargs):
    Repository.objects.sync_repositories_from_event(event)
