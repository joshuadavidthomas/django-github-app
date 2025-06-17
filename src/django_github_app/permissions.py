from __future__ import annotations

from enum import Enum
from typing import NamedTuple

import cachetools
import gidgethub

from django_github_app.github import AsyncGitHubAPI
from django_github_app.github import SyncGitHubAPI


class PermissionCacheKey(NamedTuple):
    owner: str
    repo: str
    username: str


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
        permission_str = data.get("permission", "none")
        permission = Permission.from_string(permission_str)
    except gidgethub.HTTPException as e:
        if e.status_code == 404:
            # User is not a collaborator, they have read permission if repo is public
            # Check if repo is public
            try:
                repo_data = gh.getitem(f"/repos/{owner}/{repo}")
                if not repo_data.get("private", True):
                    permission = Permission.READ
            except gidgethub.HTTPException:
                pass

    cache[cache_key] = permission
    return permission
