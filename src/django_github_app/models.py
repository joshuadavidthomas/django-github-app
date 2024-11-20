from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from django.db import models
from django.utils import timezone
from gidgethub import abc
from gidgethub import sansio
from gidgethub.apps import get_installation_access_token
from gidgethub.apps import get_jwt

from ._sync import async_to_sync_method
from ._typing import override
from .conf import app_settings
from .github import AsyncGitHubAPI
from .github import GitHubAPIEndpoint
from .github import GitHubAPIUrl


class EventLogManager(models.Manager["EventLog"]):
    async def acreate_from_event(self, event: sansio.Event):
        return await self.acreate(
            event=event.event,
            payload=event.data,
            received_at=timezone.now(),
        )

    async def acleanup_events(
        self, days_to_keep: int = app_settings.DAYS_TO_KEEP_EVENTS
    ):
        deleted = await self.filter(
            received_at__lte=timezone.now() - datetime.timedelta(days=days_to_keep)
        ).adelete()
        return deleted

    create_from_event = async_to_sync_method(acreate_from_event)
    cleanup_events = async_to_sync_method(acleanup_events)


class EventLog(models.Model):
    id: int
    event = models.CharField(max_length=255, null=True)
    payload = models.JSONField(default=None, null=True)
    received_at = models.DateTimeField(help_text="Date and time event was received")

    objects = EventLogManager()

    @override
    def __str__(self) -> str:
        ret = [str(self.pk), self.event if self.event is not None else "unknown"]
        if self.action is not None:
            ret.append(self.action)
        return " ".join(ret)

    @property
    def action(self) -> str | None:
        if self.payload is None:
            return None
        return self.payload.get("action")


class InstallationManager(models.Manager["Installation"]):
    async def acreate_from_event(self, event: sansio.Event):
        app_id = event.data["installation"]["app_id"]

        if str(app_id) == app_settings.APP_ID:
            installation = await self.acreate_from_gh_data(event.data["installation"])

            await Repository.objects.acreate_from_gh_data(
                event.data["repositories"], installation
            )

            return installation

    async def acreate_from_gh_data(self, data: dict[str, str]):
        return await self.acreate(installation_id=data["id"], data=data)

    async def aget_from_event(self, event: sansio.Event):
        try:
            installation_id = event.data["installation"]["id"]
            return await self.aget(installation_id=installation_id)
        except (Installation.DoesNotExist, KeyError):
            return None

    create_from_event = async_to_sync_method(acreate_from_event)
    create_from_gh_data = async_to_sync_method(acreate_from_gh_data)
    get_from_event = async_to_sync_method(aget_from_event)


class InstallationStatus(models.IntegerChoices):
    ACTIVE = 1, "Active"
    INACTIVE = 2, "Inactive"

    @classmethod
    def from_event(cls, event: sansio.Event) -> InstallationStatus:
        action = event.data["action"]
        match action:
            case "deleted" | "suspend":
                return cls.INACTIVE
            case "created" | "new_permissions_accepted" | "unsuspend":
                return cls.ACTIVE
            case _:
                raise ValueError(f"Unknown installation action: {action}")


class AccountType(str, Enum):
    ORG = "org"
    USER = "user"


class Installation(models.Model):
    id: int
    installation_id = models.PositiveBigIntegerField(unique=True)
    data = models.JSONField(default=dict)
    status = models.SmallIntegerField(
        choices=InstallationStatus.choices, default=InstallationStatus.ACTIVE
    )

    objects = InstallationManager()

    @override
    def __str__(self) -> str:
        return str(self.installation_id)

    def get_gh_client(self, requester: str | None = None):
        return AsyncGitHubAPI(  # pragma: no cover
            requester or self.app_slug,
            installation_id=self.installation_id,
        )

    async def aget_access_token(self, gh: abc.GitHubAPI):  # pragma: no cover
        data = await get_installation_access_token(
            gh,
            installation_id=str(self.installation_id),
            app_id=app_settings.APP_ID,
            private_key=app_settings.PRIVATE_KEY,
        )
        return data.get("token")

    async def arefresh_from_gh(self, account_type: AccountType, account_name: str):
        match account_type:
            case AccountType.ORG:
                endpoint = GitHubAPIEndpoint.ORG_APP_INSTALLATION
                url_var = "org"
            case AccountType.USER:
                endpoint = GitHubAPIEndpoint.USER_APP_INSTALLATION
                url_var = "username"
            case _:
                msg = f"`account_type` must be either 'org' or 'user', received: {account_type}"
                raise ValueError(msg)

        url = GitHubAPIUrl(endpoint=endpoint, url_vars={url_var: account_name})
        jwt = get_jwt(app_id=app_settings.APP_ID, private_key=app_settings.PRIVATE_KEY)

        async with self.get_gh_client() as gh:
            data = await gh.getitem(url.full_url, jwt=jwt)

        self.data = data
        await self.asave()

    async def aget_repos(self, params: dict[str, Any] | None = None):
        url = GitHubAPIUrl(
            GitHubAPIEndpoint.INSTALLATION_REPOS,
            params=params,
        )
        async with self.get_gh_client() as gh:
            repos = [
                repo
                async for repo in gh.getiter(url.full_url, iterable_key="repositories")
            ]
        return repos

    @property
    def app_slug(self):
        return self.data.get("app_slug", app_settings.SLUG)

    get_access_token = async_to_sync_method(aget_access_token)
    refresh_from_gh = async_to_sync_method(arefresh_from_gh)
    get_repos = async_to_sync_method(aget_repos)


class RepositoryManager(models.Manager["Repository"]):
    async def acreate_from_gh_data(
        self, data: dict[str, str] | list[dict[str, str]], installation: Installation
    ):
        if isinstance(data, list):
            repositories = [
                Repository(
                    installation=installation,
                    repository_id=repository["id"],
                    repository_node_id=repository["node_id"],
                    full_name=repository["full_name"],
                )
                for repository in data
            ]
            return await Repository.objects.abulk_create(repositories)
        else:
            return await self.acreate(
                installation=installation,
                repository_id=data["id"],
                repository_node_id=data["node_id"],
                full_name=data["full_name"],
            )

    async def aget_from_event(self, event: sansio.Event):
        try:
            repository_id = event.data["repository"]["id"]
            return await self.aget(repository_id=repository_id)
        except Repository.DoesNotExist:
            return None

    create_from_gh_data = async_to_sync_method(acreate_from_gh_data)
    get_from_event = async_to_sync_method(aget_from_event)


class Repository(models.Model):
    id: int
    installation = models.ForeignKey(
        "django_github_app.Installation",
        on_delete=models.CASCADE,
        related_name="repositories",
    )
    repository_id = models.PositiveBigIntegerField(unique=True)
    repository_node_id = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255)

    objects = RepositoryManager()

    class Meta:
        verbose_name_plural = "repositories"

    @override
    def __str__(self) -> str:
        return self.full_name

    def get_gh_client(self):
        return self.installation.get_gh_client(self.full_name)  # pragma: no cover

    async def aget_issues(self, params: dict[str, Any] | None = None):
        url = GitHubAPIUrl(
            GitHubAPIEndpoint.REPO_ISSUES,
            {"owner": self.owner, "repo": self.repo},
            params,
        )
        async with self.get_gh_client() as gh:
            issues = [issue async for issue in gh.getiter(url.full_url)]
        return issues

    @property
    def owner(self):
        return self.full_name.split("/")[0]

    @property
    def repo(self):
        return self.full_name.split("/")[1]

    get_issues = async_to_sync_method(aget_issues)
