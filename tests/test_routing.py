from __future__ import annotations

import asyncio

import pytest
from django.http import HttpRequest
from django.http import JsonResponse
from gidgethub import sansio

from django_github_app.commands import CommandScope
from django_github_app.github import SyncGitHubAPI
from django_github_app.routing import GitHubRouter
from django_github_app.views import BaseWebhookView


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
    def test_basic_mention_no_command(self, test_router):
        handler_called = False
        handler_args = None

        @test_router.mention()
        def handle_mention(event, *args, **kwargs):
            nonlocal handler_called, handler_args
            handler_called = True
            handler_args = (event, args, kwargs)

        event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot hello"}},
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called
        assert handler_args[0] == event

    def test_mention_with_command(self, test_router):
        handler_called = False

        @test_router.mention(command="help")
        def help_command(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True
            return "help response"

        event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot help"}},
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called

    def test_mention_with_scope(self, test_router):
        pr_handler_called = False

        @test_router.mention(command="deploy", scope=CommandScope.PR)
        def deploy_command(event, *args, **kwargs):
            nonlocal pr_handler_called
            pr_handler_called = True

        pr_event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot deploy"}},
            event="pull_request_review_comment",
            delivery_id="123",
        )
        test_router.dispatch(pr_event, None)

        assert pr_handler_called

        issue_event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot deploy"}},
            event="commit_comment",  # This is NOT a PR event
            delivery_id="124",
        )
        pr_handler_called = False  # Reset

        test_router.dispatch(issue_event, None)

        assert not pr_handler_called

    def test_mention_with_permission(self, test_router):
        handler_called = False

        @test_router.mention(command="delete", permission="admin")
        def delete_command(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot delete"}},
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called

    def test_case_insensitive_command(self, test_router):
        handler_called = False

        @test_router.mention(command="HELP")
        def help_command(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot help"}},
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called

    @pytest.mark.parametrize("comment", ["@bot help", "@bot h", "@bot ?"])
    def test_multiple_decorators_on_same_function(self, comment, test_router):
        call_count = 0

        @test_router.mention(command="help")
        @test_router.mention(command="h")
        @test_router.mention(command="?")
        def help_command(event, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return f"help called {call_count} times"

        event = sansio.Event(
            {"action": "created", "comment": {"body": comment}},
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert call_count == 1

    def test_async_mention_handler(self, test_router):
        handler_called = False

        @test_router.mention(command="async-test")
        async def async_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True
            return "async response"

        event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot async-test"}},
            event="issue_comment",
            delivery_id="123",
        )

        asyncio.run(test_router.adispatch(event, None))

        assert handler_called

    def test_sync_mention_handler(self, test_router):
        handler_called = False

        @test_router.mention(command="sync-test")
        def sync_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True
            return "sync response"

        event = sansio.Event(
            {"action": "created", "comment": {"body": "@bot sync-test"}},
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called

    def test_scope_validation_issue_comment_on_issue(self, test_router):
        """Test that ISSUE scope works for actual issues."""
        handler_called = False

        @test_router.mention(command="issue-only", scope=CommandScope.ISSUE)
        def issue_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Issue comment on an actual issue (no pull_request field)
        event = sansio.Event(
            {
                "action": "created",
                "issue": {"title": "Bug report", "number": 123},
                "comment": {"body": "@bot issue-only"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called

    def test_scope_validation_issue_comment_on_pr(self, test_router):
        """Test that ISSUE scope rejects PR comments."""
        handler_called = False

        @test_router.mention(command="issue-only", scope=CommandScope.ISSUE)
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
                "comment": {"body": "@bot issue-only"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert not handler_called

    def test_scope_validation_pr_scope_on_pr(self, test_router):
        """Test that PR scope works for pull requests."""
        handler_called = False

        @test_router.mention(command="pr-only", scope=CommandScope.PR)
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
                "comment": {"body": "@bot pr-only"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called

    def test_scope_validation_pr_scope_on_issue(self, test_router):
        """Test that PR scope rejects issue comments."""
        handler_called = False

        @test_router.mention(command="pr-only", scope=CommandScope.PR)
        def pr_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Issue comment on an actual issue
        event = sansio.Event(
            {
                "action": "created",
                "issue": {"title": "Bug report", "number": 123},
                "comment": {"body": "@bot pr-only"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert not handler_called

    def test_scope_validation_commit_scope(self, test_router):
        """Test that COMMIT scope works for commit comments."""
        handler_called = False

        @test_router.mention(command="commit-only", scope=CommandScope.COMMIT)
        def commit_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Commit comment event
        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot commit-only"},
                "commit": {"sha": "abc123"},
            },
            event="commit_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        assert handler_called

    def test_scope_validation_no_scope(self, test_router):
        """Test that no scope allows all comment types."""
        call_count = 0

        @test_router.mention(command="all-contexts")
        def all_handler(event, *args, **kwargs):
            nonlocal call_count
            call_count += 1

        # Test on issue
        event = sansio.Event(
            {
                "action": "created",
                "issue": {"title": "Issue", "number": 1},
                "comment": {"body": "@bot all-contexts"},
            },
            event="issue_comment",
            delivery_id="123",
        )
        test_router.dispatch(event, None)

        # Test on PR
        event = sansio.Event(
            {
                "action": "created",
                "issue": {
                    "title": "PR",
                    "number": 2,
                    "pull_request": {"url": "..."},
                },
                "comment": {"body": "@bot all-contexts"},
            },
            event="issue_comment",
            delivery_id="124",
        )
        test_router.dispatch(event, None)

        # Test on commit
        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot all-contexts"},
                "commit": {"sha": "abc123"},
            },
            event="commit_comment",
            delivery_id="125",
        )
        test_router.dispatch(event, None)

        assert call_count == 3
