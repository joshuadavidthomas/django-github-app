from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import create_autospec

import gidgethub
import pytest
from gidgethub import sansio

from django_github_app.github import AsyncGitHubAPI
from django_github_app.github import SyncGitHubAPI
from django_github_app.permissions import Permission
from django_github_app.permissions import aget_user_permission_from_event
from django_github_app.permissions import cache
from django_github_app.permissions import get_user_permission_from_event


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def create_test_event(username: str, owner: str, repo: str) -> sansio.Event:
    """Create a test event with comment author and repository info."""
    return sansio.Event(
        {
            "comment": {"user": {"login": username}},
            "repository": {"owner": {"login": owner}, "name": repo},
        },
        event="issue_comment",
        delivery_id="test",
    )


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
        event = create_test_event("user", "owner", "repo")

        permission = await aget_user_permission_from_event(event, gh)

        assert permission == Permission.ADMIN
        gh.getitem.assert_called_once_with(
            "/repos/owner/repo/collaborators/user/permission"
        )

    async def test_collaborator_with_write_permission(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(return_value={"permission": "write"})
        event = create_test_event("user", "owner", "repo")

        permission = await aget_user_permission_from_event(event, gh)

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

        event = create_test_event("user", "owner", "repo")
        permission = await aget_user_permission_from_event(event, gh)

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
        event = create_test_event("user", "owner", "repo")

        permission = await aget_user_permission_from_event(event, gh)

        assert permission == Permission.NONE

    async def test_api_error_returns_none_permission(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(
            side_effect=gidgethub.HTTPException(500, "Server error", {})
        )
        event = create_test_event("user", "owner", "repo")

        permission = await aget_user_permission_from_event(event, gh)

        assert permission == Permission.NONE

    async def test_missing_permission_field(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(return_value={})  # No permission field
        event = create_test_event("user", "owner", "repo")

        permission = await aget_user_permission_from_event(event, gh)

        assert permission == Permission.NONE


class TestGetUserPermissionSync:
    def test_collaborator_with_permission(self):
        gh = create_autospec(SyncGitHubAPI, instance=True)
        gh.getitem = Mock(return_value={"permission": "maintain"})
        event = create_test_event("user", "owner", "repo")

        permission = get_user_permission_from_event(event, gh)

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
        event = create_test_event("user", "owner", "repo")

        permission = get_user_permission_from_event(event, gh)

        assert permission == Permission.READ


class TestPermissionCaching:
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        gh.getitem = AsyncMock(return_value={"permission": "write"})
        event = create_test_event("user", "owner", "repo")

        # First call should hit the API
        perm1 = await aget_user_permission_from_event(event, gh)
        assert perm1 == Permission.WRITE
        assert gh.getitem.call_count == 1

        # Second call should use cache
        perm2 = await aget_user_permission_from_event(event, gh)
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
        event1 = create_test_event("user1", "owner", "repo")
        event2 = create_test_event("user2", "owner", "repo")

        perm1 = await aget_user_permission_from_event(event1, gh)
        perm2 = await aget_user_permission_from_event(event2, gh)

        assert perm1 == Permission.WRITE
        assert perm2 == Permission.ADMIN
        assert gh.getitem.call_count == 2

    def test_sync_cache_hit(self):
        """Test that sync version uses cache."""
        gh = create_autospec(SyncGitHubAPI, instance=True)
        gh.getitem = Mock(return_value={"permission": "read"})
        event = create_test_event("user", "owner", "repo")

        # First call should hit the API
        perm1 = get_user_permission_from_event(event, gh)
        assert perm1 == Permission.READ
        assert gh.getitem.call_count == 1

        # Second call should use cache
        perm2 = get_user_permission_from_event(event, gh)
        assert perm2 == Permission.READ
        assert gh.getitem.call_count == 1  # No additional API call


class TestPermissionFromEvent:
    @pytest.mark.asyncio
    async def test_missing_comment_data(self):
        """Test when event has no comment data."""
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        event = sansio.Event({}, event="issue_comment", delivery_id="test")

        permission = await aget_user_permission_from_event(event, gh)

        assert permission == Permission.NONE
        assert gh.getitem.called is False

    @pytest.mark.asyncio
    async def test_missing_repository_data(self):
        """Test when event has no repository data."""
        gh = create_autospec(AsyncGitHubAPI, instance=True)
        event = sansio.Event(
            {"comment": {"user": {"login": "user"}}},
            event="issue_comment",
            delivery_id="test",
        )

        permission = await aget_user_permission_from_event(event, gh)

        assert permission == Permission.NONE
        assert gh.getitem.called is False
