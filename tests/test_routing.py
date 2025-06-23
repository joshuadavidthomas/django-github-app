from __future__ import annotations

import re

import pytest
from django.http import HttpRequest
from django.http import JsonResponse

from django_github_app.github import SyncGitHubAPI
from django_github_app.mentions import MentionScope
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
    def test_mention(self, test_router, get_mock_github_api, create_event):
        calls = []

        @test_router.mention()
        def handle_mention(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event(
            "issue_comment",
            action="created",
            comment={"body": "@bot hello"},
        )

        test_router.dispatch(event, get_mock_github_api({}))

        assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_async_mention(self, test_router, aget_mock_github_api, create_event):
        calls = []

        @test_router.mention()
        async def async_handle_mention(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event(
            "issue_comment",
            action="created",
            comment={"body": "@bot async hello"},
        )

        await test_router.adispatch(event, aget_mock_github_api({}))

        assert len(calls) > 0

    @pytest.mark.parametrize(
        "username,body,expected_call_count",
        [
            ("bot", "@bot help", 1),
            ("bot", "@other-bot help", 0),
            (re.compile(r".*-bot"), "@deploy-bot start @test-bot check @user help", 2),
            (re.compile(r".*"), "@alice review @bob deploy @charlie test", 3),
            ("", "@alice review @bob deploy @charlie test", 3),
        ],
    )
    def test_mention_with_username(
        self,
        test_router,
        get_mock_github_api,
        create_event,
        username,
        body,
        expected_call_count,
    ):
        calls = []

        @test_router.mention(username=username)
        def help_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event(
            "issue_comment",
            action="created",
            comment={"body": body},
        )

        test_router.dispatch(event, get_mock_github_api({}))

        assert len(calls) == expected_call_count

    @pytest.mark.parametrize(
        "username,body,expected_call_count",
        [
            ("bot", "@bot help", 1),
            ("bot", "@other-bot help", 0),
            (re.compile(r".*-bot"), "@deploy-bot start @test-bot check @user help", 2),
            (re.compile(r".*"), "@alice review @bob deploy @charlie test", 3),
            ("", "@alice review @bob deploy @charlie test", 3),
        ],
    )
    @pytest.mark.asyncio
    async def test_async_mention_with_username(
        self,
        test_router,
        aget_mock_github_api,
        create_event,
        username,
        body,
        expected_call_count,
    ):
        calls = []

        @test_router.mention(username=username)
        async def help_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event(
            "issue_comment",
            action="created",
            comment={"body": body},
        )

        await test_router.adispatch(event, aget_mock_github_api({}))

        assert len(calls) == expected_call_count

    @pytest.mark.parametrize(
        "scope", [MentionScope.PR, MentionScope.ISSUE, MentionScope.COMMIT]
    )
    def test_mention_with_scope(
        self,
        test_router,
        get_mock_github_api,
        create_event,
        scope,
    ):
        calls = []

        @test_router.mention(scope=scope)
        def scoped_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        mock_gh = get_mock_github_api({})

        expected_events = scope.get_events()

        # Test all events that should match this scope
        for event_action in expected_events:
            # Special case: PR scope issue_comment needs pull_request field
            event_kwargs = {}
            if scope == MentionScope.PR and event_action.event == "issue_comment":
                event_kwargs["issue"] = {"pull_request": {"url": "..."}}

            event = create_event(
                event_action.event, action=event_action.action, **event_kwargs
            )

            test_router.dispatch(event, mock_gh)

        assert len(calls) == len(expected_events)

        # Test that events from other scopes don't trigger this handler
        for other_scope in MentionScope:
            if other_scope == scope:
                continue

            for event_action in other_scope.get_events():
                # Ensure the event has the right structure for its intended scope
                event_kwargs = {}
                if (
                    other_scope == MentionScope.PR
                    and event_action.event == "issue_comment"
                ):
                    event_kwargs["issue"] = {"pull_request": {"url": "..."}}
                elif (
                    other_scope == MentionScope.ISSUE
                    and event_action.event == "issue_comment"
                ):
                    # Explicitly set empty issue (no pull_request)
                    event_kwargs["issue"] = {}

                event = create_event(
                    event_action.event, action=event_action.action, **event_kwargs
                )
                test_router.dispatch(event, mock_gh)

        assert len(calls) == len(expected_events)

    @pytest.mark.parametrize(
        "scope", [MentionScope.PR, MentionScope.ISSUE, MentionScope.COMMIT]
    )
    @pytest.mark.asyncio
    async def test_async_mention_with_scope(
        self,
        test_router,
        aget_mock_github_api,
        create_event,
        scope,
    ):
        calls = []

        @test_router.mention(scope=scope)
        async def async_scoped_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        mock_gh = aget_mock_github_api({})

        expected_events = scope.get_events()

        # Test all events that should match this scope
        for event_action in expected_events:
            # Special case: PR scope issue_comment needs pull_request field
            event_kwargs = {}
            if scope == MentionScope.PR and event_action.event == "issue_comment":
                event_kwargs["issue"] = {"pull_request": {"url": "..."}}

            event = create_event(
                event_action.event, action=event_action.action, **event_kwargs
            )

            await test_router.adispatch(event, mock_gh)

        assert len(calls) == len(expected_events)

        # Test that events from other scopes don't trigger this handler
        for other_scope in MentionScope:
            if other_scope == scope:
                continue

            for event_action in other_scope.get_events():
                # Ensure the event has the right structure for its intended scope
                event_kwargs = {}
                if (
                    other_scope == MentionScope.PR
                    and event_action.event == "issue_comment"
                ):
                    event_kwargs["issue"] = {"pull_request": {"url": "..."}}
                elif (
                    other_scope == MentionScope.ISSUE
                    and event_action.event == "issue_comment"
                ):
                    # Explicitly set empty issue (no pull_request)
                    event_kwargs["issue"] = {}

                event = create_event(
                    event_action.event, action=event_action.action, **event_kwargs
                )

                await test_router.adispatch(event, mock_gh)

        assert len(calls) == len(expected_events)

    def test_issue_scope_excludes_pr_comments(
        self, test_router, get_mock_github_api, create_event
    ):
        calls = []

        @test_router.mention(scope=MentionScope.ISSUE)
        def issue_only_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        mock_gh = get_mock_github_api({})

        # Test that regular issue comments trigger the handler
        issue_event = create_event(
            "issue_comment",
            action="created",
            comment={"body": "@bot help"},
            issue={},  # No pull_request field
        )

        test_router.dispatch(issue_event, mock_gh)

        assert len(calls) == 1

        # Test that PR comments don't trigger the handler
        pr_event = create_event(
            "issue_comment",
            action="created",
            comment={"body": "@bot help"},
            issue={"pull_request": {"url": "https://github.com/test/repo/pull/1"}},
        )

        test_router.dispatch(pr_event, mock_gh)

        # Should still be 1 - no new calls
        assert len(calls) == 1

    @pytest.mark.parametrize(
        "event_kwargs,expected_call_count",
        [
            # All conditions met
            (
                {
                    "comment": {"body": "@deploy-bot deploy now"},
                    "issue": {"pull_request": {"url": "..."}},
                },
                1,
            ),
            # Wrong username
            (
                {
                    "comment": {"body": "@bot deploy now"},
                    "issue": {"pull_request": {"url": "..."}},
                },
                0,
            ),
            # Different mention text (shouldn't matter without pattern)
            (
                {
                    "comment": {"body": "@deploy-bot help"},
                    "issue": {"pull_request": {"url": "..."}},
                },
                1,
            ),
            # Wrong scope (issue instead of PR)
            (
                {
                    "comment": {"body": "@deploy-bot deploy now"},
                    "issue": {},  # No pull_request field
                },
                0,
            ),
        ],
    )
    def test_combined_mention_filters(
        self,
        test_router,
        get_mock_github_api,
        create_event,
        event_kwargs,
        expected_call_count,
    ):
        calls = []

        @test_router.mention(
            username=re.compile(r".*-bot"),
            scope=MentionScope.PR,
        )
        def combined_filter_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event("issue_comment", action="created", **event_kwargs)

        test_router.dispatch(event, get_mock_github_api({}))

        assert len(calls) == expected_call_count

    def test_mention_context(self, test_router, get_mock_github_api, create_event):
        calls = []

        @test_router.mention()
        def test_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event(
            "issue_comment",
            action="created",
            comment={"body": "@bot test"},
        )

        test_router.dispatch(event, get_mock_github_api({}))

        captured_mention = calls[0][2]["context"]

        assert captured_mention.scope.name == "ISSUE"

        triggered = captured_mention.mention

        assert triggered.username == "bot"
        assert triggered.position == 0
        assert triggered.line_info.lineno == 1

    @pytest.mark.asyncio
    async def test_async_mention_context(
        self, test_router, aget_mock_github_api, create_event
    ):
        calls = []

        @test_router.mention()
        async def async_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event(
            "issue_comment",
            action="created",
            comment={"body": "@bot async-test now"},
        )

        await test_router.adispatch(event, aget_mock_github_api({}))

        captured_mention = calls[0][2]["context"]

        assert captured_mention.scope.name == "ISSUE"

        triggered = captured_mention.mention

        assert triggered.username == "bot"
        assert triggered.position == 0
        assert triggered.line_info.lineno == 1

    def test_mention_context_multiple_mentions(
        self, test_router, get_mock_github_api, create_event
    ):
        calls = []

        @test_router.mention()
        def deploy_handler(event, *args, **kwargs):
            calls.append((event, args, kwargs))

        event = create_event(
            "issue_comment",
            action="created",
            comment={"body": "@bot help\n@second-bot deploy production"},
        )

        test_router.dispatch(event, get_mock_github_api({}))

        assert len(calls) == 2

        first = calls[0][2]["context"].mention
        second = calls[1][2]["context"].mention

        assert first.username == "bot"
        assert first.line_info.lineno == 1
        assert first.previous_mention is None
        assert first.next_mention is second

        assert second.username == "second-bot"
        assert second.line_info.lineno == 2
        assert second.previous_mention is first
        assert second.next_mention is None
