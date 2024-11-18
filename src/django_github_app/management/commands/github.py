from __future__ import annotations

from typing import Annotated
from typing import Any

from django.db import transaction
from django_typer.management import Typer
from typer import Option

from django_github_app.models import AccountType
from django_github_app.models import Installation
from django_github_app.models import Repository

cli: Typer[..., Any] = Typer(help="Manage your GitHub App")


@cli.callback()
def github(): ...


@cli.command()
def import_app(
    type: Annotated[
        AccountType,
        Option(help="The type of account the GitHub App is installed on"),
    ],
    name: Annotated[
        str,
        Option(help="The user or organization name the GitHub App is installed on"),
    ],
    installation_id: Annotated[
        int, Option(help="The installation id of the existing GitHub App")
    ],
):
    """
    Import an existing GitHub App to database Models.
    """
    with transaction.atomic():
        installation = Installation.objects.create(installation_id=installation_id)
        installation.refresh_from_gh(account_type=type, account_name=name)
        repository_data = installation.get_repos()
        Repository.objects.create_from_gh_data(repository_data, installation)
