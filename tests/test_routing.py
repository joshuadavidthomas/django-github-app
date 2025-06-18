from __future__ import annotations

import asyncio

import gidgethub
import pytest
from django.http import HttpRequest
from django.http import JsonResponse
from gidgethub import sansio

from django_github_app.github import SyncGitHubAPI
from django_github_app.mentions import MentionScope
from django_github_app.permissions import cache
from django_github_app.routing import GitHubRouter
from django_github_app.views import BaseWebhookView


@pytest.fixture(autouse=True)
def clear_permission_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def test_router():
    import django_github_app.views
    from django_github_app.routing import GitHubRouter

    old_routers = GitHubRouter._routers.copy()
    GitHubRouter._routers = []

    old_router = django_github_app.views._router

    test_router = GitHubRouter()
    django_github_app.views._router = test_router

    yield test_router

    GitHubRouter._routers = old_routers
    django_github_app.views._router = old_router


class View(BaseWebhookView[SyncGitHubAPI]):
    github_api_class = SyncGitHubAPI

    def post(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({})


class LegacyView(BaseWebhookView[SyncGitHubAPI]):
    github_api_class = SyncGitHubAPI

    @property
    def router(self) -> GitHubRouter:
        # Always create a new router (simulating issue #73)
        return GitHubRouter(*GitHubRouter.routers)

    def post(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({})


class TestGitHubRouter:
    def test_router_single_instance(self):
        view1 = View()
        view2 = View()

        router1 = view1.router
        router2 = view2.router

        assert router1 is router2
        assert view1.router is router1
        assert view2.router is router2

    def test_no_duplicate_routers(self):
        router_ids = set()

        for _ in range(1000):
            view = View()
            router_ids.add(id(view.router))

        assert len(router_ids) == 1

    def test_duplicate_routers_without_module_level_router(self):
        router_ids = set()

        for _ in range(5):
            view = LegacyView()
            router_ids.add(id(view.router))

        assert len(router_ids) == 5

    @pytest.mark.limit_memory("1.5MB")
    @pytest.mark.xdist_group(group="memory_tests")
    def test_router_memory_stress_test(self):
        view_count = 10000
        views = []

        for _ in range(view_count):
            view = View()
            views.append(view)

        view1_router = views[0].router

        assert len(views) == view_count
        assert all(view.router is view1_router for view in views)

    @pytest.mark.limit_memory("1.5MB")
    @pytest.mark.xdist_group(group="memory_tests")
    @pytest.mark.skip(
        "does not reliably allocate memory when run with other memory test"
    )
    def test_router_memory_stress_test_legacy(self):
        view_count = 10000
        views = []

        for _ in range(view_count):
            view = LegacyView()
            views.append(view)

        view1_router = views[0].router

        assert len(views) == view_count
        assert not all(view.router is view1_router for view in views)


class TestMentionDecorator:
    def test_basic_mention_no_command(self, test_router, get_mock_github_api_sync):
        handler_called = False
        handler_args = None

        @test_router.mention()
        def handle_mention(event, *args, **kwargs):
            nonlocal handler_called, handler_args
            handler_called = True
            handler_args = (event, args, kwargs)

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot hello", "user": {"login": "testuser"}},
                "issue": {"number": 1},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert handler_args[0] == event

    def test_mention_with_command(self, test_router, get_mock_github_api_sync):
        handler_called = False

        @test_router.mention(command="help")
        def help_command(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True
            return "help response"

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot help", "user": {"login": "testuser"}},
                "issue": {"number": 2},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_mention_with_scope(self, test_router, get_mock_github_api_sync):
        pr_handler_called = False

        @test_router.mention(command="deploy", scope=MentionScope.PR)
        def deploy_command(event, *args, **kwargs):
            nonlocal pr_handler_called
            pr_handler_called = True

        mock_gh = get_mock_github_api_sync({"permission": "write"})

        pr_event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot deploy", "user": {"login": "testuser"}},
                "pull_request": {"number": 3},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="pull_request_review_comment",
            delivery_id="123",
        )
        test_router.dispatch(pr_event, mock_gh)

        assert pr_handler_called

        issue_event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot deploy", "user": {"login": "testuser"}},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="commit_comment",  # This is NOT a PR event
            delivery_id="124",
        )
        pr_handler_called = False  # Reset

        test_router.dispatch(issue_event, mock_gh)

        assert not pr_handler_called

    def test_mention_with_permission(self, test_router, get_mock_github_api_sync):
        handler_called = False

        @test_router.mention(command="delete", permission="admin")
        def delete_command(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot delete", "user": {"login": "testuser"}},
                "issue": {
                    "number": 123
                },  # Added issue field required for issue_comment events
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        # Mock the permission check to return admin permission
        mock_gh = get_mock_github_api_sync({"permission": "admin"})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_case_insensitive_command(self, test_router, get_mock_github_api_sync):
        handler_called = False

        @test_router.mention(command="HELP")
        def help_command(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot help", "user": {"login": "testuser"}},
                "issue": {"number": 4},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    @pytest.mark.parametrize("comment", ["@bot help", "@bot h", "@bot ?"])
    def test_multiple_decorators_on_same_function(
        self, comment, test_router, get_mock_github_api_sync
    ):
        call_count = 0

        @test_router.mention(command="help")
        @test_router.mention(command="h")
        @test_router.mention(command="?")
        def help_command(event, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return f"help called {call_count} times"

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": comment, "user": {"login": "testuser"}},
                "issue": {"number": 5},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert call_count == 1

    def test_async_mention_handler(self, test_router, get_mock_github_api):
        handler_called = False

        @test_router.mention(command="async-test")
        async def async_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True
            return "async response"

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot async-test", "user": {"login": "testuser"}},
                "issue": {"number": 1},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )

        mock_gh = get_mock_github_api({"permission": "write"})
        asyncio.run(test_router.adispatch(event, mock_gh))

        assert handler_called

    def test_sync_mention_handler(self, test_router, get_mock_github_api_sync):
        handler_called = False

        @test_router.mention(command="sync-test")
        def sync_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True
            return "sync response"

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot sync-test", "user": {"login": "testuser"}},
                "issue": {"number": 6},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_issue_comment_on_issue(
        self, test_router, get_mock_github_api_sync
    ):
        """Test that ISSUE scope works for actual issues."""
        handler_called = False

        @test_router.mention(command="issue-only", scope=MentionScope.ISSUE)
        def issue_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Issue comment on an actual issue (no pull_request field)
        event = sansio.Event(
            {
                "action": "created",
                "issue": {"title": "Bug report", "number": 123},
                "comment": {"body": "@bot issue-only", "user": {"login": "testuser"}},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_issue_comment_on_pr(
        self, test_router, get_mock_github_api_sync
    ):
        """Test that ISSUE scope rejects PR comments."""
        handler_called = False

        @test_router.mention(command="issue-only", scope=MentionScope.ISSUE)
        def issue_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Issue comment on a pull request (has pull_request field)
        event = sansio.Event(
            {
                "action": "created",
                "issue": {
                    "title": "PR title",
                    "number": 456,
                    "pull_request": {"url": "https://api.github.com/..."},
                },
                "comment": {"body": "@bot issue-only", "user": {"login": "testuser"}},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert not handler_called

    def test_scope_validation_pr_scope_on_pr(
        self, test_router, get_mock_github_api_sync
    ):
        """Test that PR scope works for pull requests."""
        handler_called = False

        @test_router.mention(command="pr-only", scope=MentionScope.PR)
        def pr_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Issue comment on a pull request
        event = sansio.Event(
            {
                "action": "created",
                "issue": {
                    "title": "PR title",
                    "number": 456,
                    "pull_request": {"url": "https://api.github.com/..."},
                },
                "comment": {"body": "@bot pr-only", "user": {"login": "testuser"}},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_pr_scope_on_issue(
        self, test_router, get_mock_github_api_sync
    ):
        """Test that PR scope rejects issue comments."""
        handler_called = False

        @test_router.mention(command="pr-only", scope=MentionScope.PR)
        def pr_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Issue comment on an actual issue
        event = sansio.Event(
            {
                "action": "created",
                "issue": {"title": "Bug report", "number": 123},
                "comment": {"body": "@bot pr-only", "user": {"login": "testuser"}},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert not handler_called

    def test_scope_validation_commit_scope(self, test_router, get_mock_github_api_sync):
        """Test that COMMIT scope works for commit comments."""
        handler_called = False

        @test_router.mention(command="commit-only", scope=MentionScope.COMMIT)
        def commit_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Commit comment event
        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot commit-only", "user": {"login": "testuser"}},
                "commit": {"sha": "abc123"},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="commit_comment",
            delivery_id="123",
        )
        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_no_scope(self, test_router, get_mock_github_api_sync):
        """Test that no scope allows all comment types."""
        call_count = 0

        @test_router.mention(command="all-contexts")
        def all_handler(event, *args, **kwargs):
            nonlocal call_count
            call_count += 1

        mock_gh = get_mock_github_api_sync({"permission": "write"})

        # Test on issue
        event = sansio.Event(
            {
                "action": "created",
                "issue": {"title": "Issue", "number": 1},
                "comment": {"body": "@bot all-contexts", "user": {"login": "testuser"}},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, mock_gh)

        # Test on PR
        event = sansio.Event(
            {
                "action": "created",
                "issue": {
                    "title": "PR",
                    "number": 2,
                    "pull_request": {"url": "..."},
                },
                "comment": {"body": "@bot all-contexts", "user": {"login": "testuser"}},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="124",
        )
        test_router.dispatch(event, mock_gh)

        # Test on commit
        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot all-contexts", "user": {"login": "testuser"}},
                "commit": {"sha": "abc123"},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="commit_comment",
            delivery_id="125",
        )
        test_router.dispatch(event, mock_gh)

        assert call_count == 3

    def test_mention_enrichment_with_permission(
        self, test_router, get_mock_github_api_sync
    ):
        """Test that mention decorator enriches kwargs with permission data."""
        handler_called = False
        captured_kwargs = {}

        @test_router.mention(command="admin-only", permission="admin")
        def admin_command(event, *args, **kwargs):
            nonlocal handler_called, captured_kwargs
            handler_called = True
            captured_kwargs = kwargs.copy()

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot admin-only", "user": {"login": "testuser"}},
                "issue": {"number": 123},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )

        # Mock the permission check to return write permission (less than admin)
        mock_gh = get_mock_github_api_sync({"permission": "write"})

        test_router.dispatch(event, mock_gh)

        # Handler SHOULD be called with enriched data
        assert handler_called
        assert "mention" in captured_kwargs
        mention = captured_kwargs["mention"]
        assert mention.commands == ["admin-only"]
        assert mention.user_permission.name == "WRITE"
        assert mention.scope.name == "ISSUE"

    def test_mention_enrichment_no_permission(
        self, test_router, get_mock_github_api_sync
    ):
        """Test enrichment when user has no permission."""
        handler_called = False
        captured_kwargs = {}

        @test_router.mention(command="write-required", permission="write")
        def write_command(event, *args, **kwargs):
            nonlocal handler_called, captured_kwargs
            handler_called = True
            captured_kwargs = kwargs.copy()

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot write-required",
                    "user": {"login": "stranger"},
                },
                "issue": {"number": 456},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="456",
        )

        # Mock returns 404 for non-collaborator
        mock_gh = get_mock_github_api_sync({})  # Empty dict as we'll override getitem
        mock_gh.getitem.side_effect = [
            gidgethub.HTTPException(404, "Not found", {}),  # User is not a collaborator
            {"private": True},  # Repo is private
        ]

        test_router.dispatch(event, mock_gh)

        # Handler SHOULD be called with enriched data
        assert handler_called
        assert "mention" in captured_kwargs
        mention = captured_kwargs["mention"]
        assert mention.commands == ["write-required"]
        assert mention.user_permission.name == "NONE"  # User has no permission
        assert mention.scope.name == "ISSUE"

    @pytest.mark.asyncio
    async def test_async_mention_enrichment(self, test_router, get_mock_github_api):
        """Test async mention decorator enriches kwargs."""
        handler_called = False
        captured_kwargs = {}

        @test_router.mention(command="maintain-only", permission="maintain")
        async def maintain_command(event, *args, **kwargs):
            nonlocal handler_called, captured_kwargs
            handler_called = True
            captured_kwargs = kwargs.copy()

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot maintain-only",
                    "user": {"login": "contributor"},
                },
                "issue": {"number": 789},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="789",
        )

        # Mock the permission check to return triage permission (less than maintain)
        mock_gh = get_mock_github_api({"permission": "triage"})

        await test_router.adispatch(event, mock_gh)

        # Handler SHOULD be called with enriched data
        assert handler_called
        assert "mention" in captured_kwargs
        mention = captured_kwargs["mention"]
        assert mention.commands == ["maintain-only"]
        assert mention.user_permission.name == "TRIAGE"
        assert mention.scope.name == "ISSUE"

    def test_mention_enrichment_pr_scope(self, test_router, get_mock_github_api_sync):
        """Test that PR comments get correct scope enrichment."""
        handler_called = False
        captured_kwargs = {}

        @test_router.mention(command="deploy")
        def deploy_command(event, *args, **kwargs):
            nonlocal handler_called, captured_kwargs
            handler_called = True
            captured_kwargs = kwargs.copy()

        # Issue comment on a PR (has pull_request field)
        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot deploy", "user": {"login": "dev"}},
                "issue": {
                    "number": 42,
                    "pull_request": {
                        "url": "https://api.github.com/repos/test/repo/pulls/42"
                    },
                },
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="999",
        )

        mock_gh = get_mock_github_api_sync({"permission": "write"})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert "mention" in captured_kwargs
        mention = captured_kwargs["mention"]
        assert mention.commands == ["deploy"]
        assert mention.user_permission.name == "WRITE"
        assert mention.scope.name == "PR"  # Should be PR, not ISSUE
