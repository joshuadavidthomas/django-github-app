from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import create_autospec

import gidgethub
import pytest

from django_github_app.github import AsyncGitHubAPI
from django_github_app.github import SyncGitHubAPI
from django_github_app.permissions import Permission
from django_github_app.permissions import aget_user_permission
from django_github_app.permissions import cache
from django_github_app.permissions import get_user_permission


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestPermission:
    def test_permission_ordering(self):
        assert Permission.NONE < Permission.READ
        assert Permission.READ < Permission.TRIAGE
        assert Permission.TRIAGE < Permission.WRITE
        assert Permission.WRITE < Permission.MAINTAIN
        assert Permission.MAINTAIN < Permission.ADMIN

        assert Permission.ADMIN > Permission.WRITE
        assert Permission.WRITE >= Permission.WRITE
        assert Permission.READ <= Permission.TRIAGE

    @pytest.mark.parametrize(
        "permission_str,expected",
        [
            ("read", Permission.READ),
            ("Read", Permission.READ),
            ("READ", Permission.READ),
            (" read ", Permission.READ),
            ("triage", Permission.TRIAGE),
            ("write", Permission.WRITE),
            ("maintain", Permission.MAINTAIN),
            ("admin", Permission.ADMIN),
            ("none", Permission.NONE),
        ],
    )
    def test_from_string(self, permission_str, expected):
        assert Permission.from_string(permission_str) == expected

    def test_from_string_invalid(self):
        with pytest.raises(ValueError, match="Unknown permission level: invalid"):
            Permission.from_string("invalid")

        with pytest.raises(ValueError, match="Unknown permission level: owner"):
            Permission.from_string("owner")


@pytest.mark.asyncio
class TestGetUserPermission:
    async def test_collaborator_with_admin_permission(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(return_value={"permission": "admin"})

        permission = await aget_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.ADMIN
        gh.getitem.assert_called_once_with(
            "/repos/owner/repo/collaborators/user/permission"
        )

    async def test_collaborator_with_write_permission(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(return_value={"permission": "write"})

        permission = await aget_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.WRITE

    async def test_non_collaborator_public_repo(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        # First call returns 404 (not a collaborator)
        gh.getitem = AsyncMock(
            side_effect=[
                gidgethub.HTTPException(404, "Not found", {}),
                {"private": False},  # Repo is public
            ]
        )

        permission = await aget_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.READ
        assert gh.getitem.call_count == 2
        gh.getitem.assert_any_call("/repos/owner/repo/collaborators/user/permission")
        gh.getitem.assert_any_call("/repos/owner/repo")

    async def test_non_collaborator_private_repo(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        # First call returns 404 (not a collaborator)
        gh.getitem = AsyncMock(
            side_effect=[
                gidgethub.HTTPException(404, "Not found", {}),
                {"private": True},  # Repo is private
            ]
        )

        permission = await aget_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.NONE

    async def test_api_error_returns_none_permission(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(
            side_effect=gidgethub.HTTPException(500, "Server error", {})
        )

        permission = await aget_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.NONE

    async def test_missing_permission_field(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(return_value={})  # No permission field

        permission = await aget_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.NONE


class TestGetUserPermissionSync:
    def test_collaborator_with_permission(self):
        gh = create_autospec(SyncGitHubAPI, instance=True)
        gh.getitem = Mock(return_value={"permission": "maintain"})

        permission = get_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.MAINTAIN
        gh.getitem.assert_called_once_with(
            "/repos/owner/repo/collaborators/user/permission"
        )

    def test_non_collaborator_public_repo(self):
        gh = create_autospec(SyncGitHubAPI, instance=True)
        # First call returns 404 (not a collaborator)
        gh.getitem = Mock(
            side_effect=[
                gidgethub.HTTPException(404, "Not found", {}),
                {"private": False},  # Repo is public
            ]
        )

        permission = get_user_permission(gh, "owner", "repo", "user")

        assert permission == Permission.READ


class TestPermissionCaching:
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(return_value={"permission": "write"})

        # First call should hit the API
        perm1 = await aget_user_permission(gh, "owner", "repo", "user")
        assert perm1 == Permission.WRITE
        assert gh.getitem.call_count == 1

        # Second call should use cache
        perm2 = await aget_user_permission(gh, "owner", "repo", "user")
        assert perm2 == Permission.WRITE
        assert gh.getitem.call_count == 1  # No additional API call

    @pytest.mark.asyncio
    async def test_cache_different_users(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(
            side_effect=[
                {"permission": "write"},
                {"permission": "admin"},
            ]
        )

        perm1 = await aget_user_permission(gh, "owner", "repo", "user1")
        perm2 = await aget_user_permission(gh, "owner", "repo", "user2")

        assert perm1 == Permission.WRITE
        assert perm2 == Permission.ADMIN
        assert gh.getitem.call_count == 2

    def test_sync_cache_hit(self):
        """Test that sync version uses cache."""
        gh = create_autospec(SyncGitHubAPI, instance=True)
        gh.getitem = Mock(return_value={"permission": "read"})

        # First call should hit the API
        perm1 = get_user_permission(gh, "owner", "repo", "user")
        assert perm1 == Permission.READ
        assert gh.getitem.call_count == 1

        # Second call should use cache
        perm2 = get_user_permission(gh, "owner", "repo", "user")
        assert perm2 == Permission.READ
        assert gh.getitem.call_count == 1  # No additional API call
