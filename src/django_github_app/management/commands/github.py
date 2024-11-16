from __future__ import annotations

from typing import Annotated
from typing import Literal

from asgiref.sync import async_to_sync
from django_typer.management import Typer
from typer import Option

from django_github_app.conf import app_settings
from django_github_app.github import AsyncGitHubAPI
from django_github_app.github import GitHubAPIEndpoint
from django_github_app.github import GitHubAPIUrl
from django_github_app.models import Installation
from django_github_app.models import Repository

cli = Typer(help="Manage your GitHub App")


async def get_installation(name, installation_id, oauth_token):
    async with AsyncGitHubAPI(app_settings.SLUG) as gh:
        gh.oauth_token = oauth_token
        endpoint = GitHubAPIUrl(
            GitHubAPIEndpoint.ORG_INSTALLATIONS,
            {"org": name},
        )
        data = await gh.getitem(endpoint.full_url)
        for installation in data.get("installations"):
            if installation["id"] == installation_id:
                return installation
        return None


async def get_repos(installation):
    async with AsyncGitHubAPI(installation.app_slug) as gh:
        gh.oauth_token = await installation.aget_access_token(gh)
        url = GitHubAPIUrl(GitHubAPIEndpoint.INSTALLATION_REPOS)
        repos = [
            repo async for repo in gh.getiter(url.full_url, iterable_key="repositories")
        ]
        print(f"{repos=}")


@cli.command()
def import_app(
    name: Annotated[
        str,
        Option(
            help="The name of the user, repository (owner/repo), or organization the GitHub App is installed on"
        ),
    ],
    type: Annotated[
        Literal["user", "repo", "org"],
        Option(help="The type of account the GitHub App is installed on"),
    ],
    installation_id: Annotated[
        int, Option(help="The installation id of the existing GitHub App")
    ],
    oauth_token: Annotated[
        str, Option(help="PAT for accessing GitHub App installations")
    ],
):
    """
    Import an existing GitHub App to database Models.
    """
    installation_data = async_to_sync(get_installation)(
        name, installation_id, oauth_token
    )
    if installation_data:
        installation = Installation.objects.create_from_gh_data(installation_data)
        repository_data = installation.get_repos()
        Repository.objects.create_from_gh_data(repository_data)
