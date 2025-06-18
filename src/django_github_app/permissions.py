from __future__ import annotations

from enum import Enum
from typing import NamedTuple

import cachetools
import gidgethub
from gidgethub import sansio

from django_github_app.github import AsyncGitHubAPI
from django_github_app.github import SyncGitHubAPI


class Permission(int, Enum):
    NONE = 0
    READ = 1
    TRIAGE = 2
    WRITE = 3
    MAINTAIN = 4
    ADMIN = 5

    @classmethod
    def from_string(cls, permission: str) -> Permission:
        permission_map = {
            "none": cls.NONE,
            "read": cls.READ,
            "triage": cls.TRIAGE,
            "write": cls.WRITE,
            "maintain": cls.MAINTAIN,
            "admin": cls.ADMIN,
        }

        normalized = permission.lower().strip()
        if normalized not in permission_map:
            raise ValueError(f"Unknown permission level: {permission}")

        return permission_map[normalized]


cache: cachetools.LRUCache[PermissionCacheKey, Permission] = cachetools.LRUCache(
    maxsize=128
)


class PermissionCacheKey(NamedTuple):
    owner: str
    repo: str
    username: str


async def aget_user_permission(
    gh: AsyncGitHubAPI, owner: str, repo: str, username: str
) -> Permission:
    cache_key = PermissionCacheKey(owner, repo, username)

    if cache_key in cache:
        return cache[cache_key]

    permission = Permission.NONE

    try:
        # Check if user is a collaborator and get their permission
        data = await gh.getitem(
            f"/repos/{owner}/{repo}/collaborators/{username}/permission"
        )
        permission_str = data.get("permission", "none")
        permission = Permission.from_string(permission_str)
    except gidgethub.HTTPException as e:
        if e.status_code == 404:
            # User is not a collaborator, they have read permission if repo is public
            # Check if repo is public
            try:
                repo_data = await gh.getitem(f"/repos/{owner}/{repo}")
                if not repo_data.get("private", True):
                    permission = Permission.READ
            except gidgethub.HTTPException:
                pass

    cache[cache_key] = permission
    return permission


def get_user_permission(
    gh: SyncGitHubAPI, owner: str, repo: str, username: str
) -> Permission:
    cache_key = PermissionCacheKey(owner, repo, username)

    if cache_key in cache:
        return cache[cache_key]

    permission = Permission.NONE

    try:
        # Check if user is a collaborator and get their permission
        data = gh.getitem(f"/repos/{owner}/{repo}/collaborators/{username}/permission")
        permission_str = data.get("permission", "none")  # type: ignore[attr-defined]
        permission = Permission.from_string(permission_str)
    except gidgethub.HTTPException as e:
        if e.status_code == 404:
            # User is not a collaborator, they have read permission if repo is public
            # Check if repo is public
            try:
                repo_data = gh.getitem(f"/repos/{owner}/{repo}")
                if not repo_data.get("private", True):  # type: ignore[attr-defined]
                    permission = Permission.READ
            except gidgethub.HTTPException:
                pass

    cache[cache_key] = permission
    return permission


class EventInfo(NamedTuple):
    comment_author: str | None
    owner: str | None
    repo: str | None

    @classmethod
    def from_event(cls, event: sansio.Event) -> EventInfo:
        comment_author = None
        owner = None
        repo = None

        if "comment" in event.data:
            comment_author = event.data["comment"]["user"]["login"]

        if "repository" in event.data:
            owner = event.data["repository"]["owner"]["login"]
            repo = event.data["repository"]["name"]

        return cls(comment_author=comment_author, owner=owner, repo=repo)


class PermissionCheck(NamedTuple):
    has_permission: bool


async def aget_user_permission_from_event(
    event: sansio.Event, gh: AsyncGitHubAPI
) -> Permission | None:
    comment_author, owner, repo = EventInfo.from_event(event)

    if not (comment_author and owner and repo):
        return None

    return await aget_user_permission(gh, owner, repo, comment_author)


async def acheck_mention_permission(
    event: sansio.Event, gh: AsyncGitHubAPI, required_permission: Permission
) -> PermissionCheck:
    user_permission = await aget_user_permission_from_event(event, gh)

    if user_permission is None:
        return PermissionCheck(has_permission=False)

    return PermissionCheck(has_permission=user_permission >= required_permission)


def get_user_permission_from_event(
    event: sansio.Event, gh: SyncGitHubAPI
) -> Permission | None:
    comment_author, owner, repo = EventInfo.from_event(event)

    if not (comment_author and owner and repo):
        return None

    return get_user_permission(gh, owner, repo, comment_author)


def check_mention_permission(
    event: sansio.Event, gh: SyncGitHubAPI, required_permission: Permission
) -> PermissionCheck:
    user_permission = get_user_permission_from_event(event, gh)

    if user_permission is None:
        return PermissionCheck(has_permission=False)

    return PermissionCheck(has_permission=user_permission >= required_permission)
