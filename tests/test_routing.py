from __future__ import annotations

import asyncio
import re

import pytest
from django.http import HttpRequest
from django.http import JsonResponse
from gidgethub import sansio

from django_github_app.github import SyncGitHubAPI
from django_github_app.mentions import MentionScope
from django_github_app.routing import GitHubRouter
from django_github_app.views import BaseWebhookView


@pytest.fixture(autouse=True)
def setup_test_app_name(override_app_settings):
    with override_app_settings(NAME="bot"):
        yield


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
    def test_basic_mention_no_pattern(self, test_router, get_mock_github_api):
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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert handler_args[0] == event

    def test_mention_with_pattern(self, test_router, get_mock_github_api):
        handler_called = False

        @test_router.mention(pattern="help")
        def help_handler(event, *args, **kwargs):
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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_mention_with_scope(self, test_router, get_mock_github_api):
        pr_handler_called = False

        @test_router.mention(pattern="deploy", scope=MentionScope.PR)
        def deploy_handler(event, *args, **kwargs):
            nonlocal pr_handler_called
            pr_handler_called = True

        mock_gh = get_mock_github_api({})

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

    def test_case_insensitive_pattern(self, test_router, get_mock_github_api):
        handler_called = False

        @test_router.mention(pattern="HELP")
        def help_handler(event, *args, **kwargs):
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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_multiple_decorators_on_same_function(
        self, test_router, get_mock_github_api
    ):
        call_counts = {"help": 0, "h": 0, "?": 0}

        @test_router.mention(pattern="help")
        @test_router.mention(pattern="h")
        @test_router.mention(pattern="?")
        def help_handler(event, *args, **kwargs):
            mention = kwargs.get("context")
            if mention and mention.mention:
                text = mention.mention.text.strip()
                if text in call_counts:
                    call_counts[text] += 1

        for pattern in ["help", "h", "?"]:
            event = sansio.Event(
                {
                    "action": "created",
                    "comment": {
                        "body": f"@bot {pattern}",
                        "user": {"login": "testuser"},
                    },
                    "issue": {"number": 5},
                    "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
                },
                event="issue_comment",
                delivery_id=f"123-{pattern}",
            )
            mock_gh = get_mock_github_api({})
            test_router.dispatch(event, mock_gh)

        # Check expected behavior:
        # - "help" matches both "help" pattern and "h" pattern (since "help" starts with "h")
        # - "h" matches only "h" pattern
        # - "?" matches only "?" pattern
        assert call_counts["help"] == 2  # Matched by both "help" and "h" patterns
        assert call_counts["h"] == 1  # Matched only by "h" pattern
        assert call_counts["?"] == 1  # Matched only by "?" pattern

    def test_async_mention_handler(self, test_router, aget_mock_github_api):
        handler_called = False

        @test_router.mention(pattern="async-test")
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

        mock_gh = aget_mock_github_api({})
        asyncio.run(test_router.adispatch(event, mock_gh))

        assert handler_called

    def test_sync_mention_handler(self, test_router, get_mock_github_api):
        handler_called = False

        @test_router.mention(pattern="sync-test")
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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_issue_comment_on_issue(
        self, test_router, get_mock_github_api
    ):
        handler_called = False

        @test_router.mention(pattern="issue-only", scope=MentionScope.ISSUE)
        def issue_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_issue_comment_on_pr(
        self, test_router, get_mock_github_api
    ):
        handler_called = False

        @test_router.mention(pattern="issue-only", scope=MentionScope.ISSUE)
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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert not handler_called

    def test_scope_validation_pr_scope_on_pr(self, test_router, get_mock_github_api):
        handler_called = False

        @test_router.mention(pattern="pr-only", scope=MentionScope.PR)
        def pr_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_pr_scope_on_issue(self, test_router, get_mock_github_api):
        handler_called = False

        @test_router.mention(pattern="pr-only", scope=MentionScope.PR)
        def pr_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert not handler_called

    def test_scope_validation_commit_scope(self, test_router, get_mock_github_api):
        """Test that COMMIT scope works for commit comments."""
        handler_called = False

        @test_router.mention(pattern="commit-only", scope=MentionScope.COMMIT)
        def commit_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

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
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

    def test_scope_validation_no_scope(self, test_router, get_mock_github_api):
        call_count = 0

        @test_router.mention(pattern="all-contexts")
        def all_handler(event, *args, **kwargs):
            nonlocal call_count
            call_count += 1

        mock_gh = get_mock_github_api({})

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

    def test_mention_enrichment_pr_scope(self, test_router, get_mock_github_api):
        handler_called = False
        captured_kwargs = {}

        @test_router.mention(pattern="deploy")
        def deploy_handler(event, *args, **kwargs):
            nonlocal handler_called, captured_kwargs
            handler_called = True
            captured_kwargs = kwargs.copy()

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

        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert "context" in captured_kwargs

        mention = captured_kwargs["context"]

        assert mention.comment.body == "@bot deploy"
        assert mention.mention.text == "deploy"
        assert mention.scope.name == "PR"


class TestUpdatedMentionContext:
    def test_mention_context_structure(self, test_router, get_mock_github_api):
        handler_called = False
        captured_mention = None

        @test_router.mention(pattern="test")
        def test_handler(event, *args, **kwargs):
            nonlocal handler_called, captured_mention
            handler_called = True
            captured_mention = kwargs.get("context")

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot test",
                    "user": {"login": "testuser"},
                    "created_at": "2024-01-01T12:00:00Z",
                    "html_url": "https://github.com/test/repo/issues/1#issuecomment-123",
                },
                "issue": {"number": 1},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="123",
        )

        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

        comment = captured_mention.comment

        assert comment.body == "@bot test"
        assert comment.author == "testuser"
        assert comment.url == "https://github.com/test/repo/issues/1#issuecomment-123"
        assert len(comment.mentions) == 1

        triggered = captured_mention.mention

        assert triggered.username == "bot"
        assert triggered.text == "test"
        assert triggered.position == 0
        assert triggered.line_info.lineno == 1

        assert captured_mention.scope.name == "ISSUE"

    def test_multiple_mentions_mention(self, test_router, get_mock_github_api):
        handler_called = False
        captured_mention = None

        @test_router.mention(pattern="deploy")
        def deploy_handler(event, *args, **kwargs):
            nonlocal handler_called, captured_mention
            handler_called = True
            captured_mention = kwargs.get("context")

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot help\n@bot deploy production",
                    "user": {"login": "testuser"},
                    "created_at": "2024-01-01T12:00:00Z",
                    "html_url": "https://github.com/test/repo/issues/2#issuecomment-456",
                },
                "issue": {"number": 2},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="456",
        )

        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert captured_mention is not None
        assert len(captured_mention.comment.mentions) == 2
        assert captured_mention.mention.text == "deploy production"
        assert captured_mention.mention.line_info.lineno == 2

        first_mention = captured_mention.comment.mentions[0]
        second_mention = captured_mention.comment.mentions[1]

        assert first_mention.next_mention is second_mention
        assert second_mention.previous_mention is first_mention

    def test_mention_without_pattern(self, test_router, get_mock_github_api):
        handler_called = False
        captured_mention = None

        @test_router.mention()  # No pattern specified
        def general_handler(event, *args, **kwargs):
            nonlocal handler_called, captured_mention
            handler_called = True
            captured_mention = kwargs.get("context")

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot can you help me?",
                    "user": {"login": "testuser"},
                    "created_at": "2024-01-01T12:00:00Z",
                    "html_url": "https://github.com/test/repo/issues/3#issuecomment-789",
                },
                "issue": {"number": 3},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="789",
        )

        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert captured_mention.mention.text == "can you help me?"
        assert captured_mention.mention.username == "bot"

    @pytest.mark.asyncio
    async def test_async_mention_context_structure(
        self, test_router, aget_mock_github_api
    ):
        handler_called = False
        captured_mention = None

        @test_router.mention(pattern="async-test")
        async def async_handler(event, *args, **kwargs):
            nonlocal handler_called, captured_mention
            handler_called = True
            captured_mention = kwargs.get("context")

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot async-test now",
                    "user": {"login": "asyncuser"},
                    "created_at": "2024-01-01T13:00:00Z",
                    "html_url": "https://github.com/test/repo/issues/4#issuecomment-999",
                },
                "issue": {"number": 4},
                "repository": {"owner": {"login": "testowner"}, "name": "testrepo"},
            },
            event="issue_comment",
            delivery_id="999",
        )

        mock_gh = aget_mock_github_api({})
        await test_router.adispatch(event, mock_gh)

        assert handler_called
        assert captured_mention.comment.body == "@bot async-test now"
        assert captured_mention.mention.text == "async-test now"


class TestFlexibleMentionTriggers:
    def test_pattern_parameter_string(self, test_router, get_mock_github_api):
        handler_called = False
        captured_mention = None

        @test_router.mention(pattern="deploy")
        def deploy_handler(event, *args, **kwargs):
            nonlocal handler_called, captured_mention
            handler_called = True
            captured_mention = kwargs.get("context")

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot deploy production",
                    "user": {"login": "user"},
                },
                "issue": {"number": 1},
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert captured_mention.mention.match is not None
        assert captured_mention.mention.match.group(0) == "deploy"

        # Should not match - pattern in middle
        handler_called = False
        event.data["comment"]["body"] = "@bot please deploy"
        test_router.dispatch(event, mock_gh)

        assert not handler_called

    def test_pattern_parameter_regex(self, test_router, get_mock_github_api):
        handler_called = False
        captured_mention = None

        @test_router.mention(pattern=re.compile(r"deploy-(?P<env>prod|staging|dev)"))
        def deploy_env_handler(event, *args, **kwargs):
            nonlocal handler_called, captured_mention
            handler_called = True
            captured_mention = kwargs.get("context")

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot deploy-staging", "user": {"login": "user"}},
                "issue": {"number": 1},
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called
        assert captured_mention.mention.match is not None
        assert captured_mention.mention.match.group("env") == "staging"

    def test_username_parameter_exact(self, test_router, get_mock_github_api):
        handler_called = False

        @test_router.mention(username="deploy-bot")
        def deploy_bot_handler(event, *args, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Should match deploy-bot
        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@deploy-bot run tests", "user": {"login": "user"}},
                "issue": {"number": 1},
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert handler_called

        # Should not match bot
        handler_called = False
        event.data["comment"]["body"] = "@bot run tests"
        test_router.dispatch(event, mock_gh)

        assert not handler_called

    def test_username_parameter_regex(self, test_router, get_mock_github_api):
        handler_count = 0

        @test_router.mention(username=re.compile(r".*-bot"))
        def any_bot_handler(event, *args, **kwargs):
            nonlocal handler_count
            handler_count += 1

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@deploy-bot start @test-bot check @user help",
                    "user": {"login": "user"},
                },
                "issue": {"number": 1},
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        # Should be called twice (deploy-bot and test-bot)
        assert handler_count == 2

    def test_username_all_mentions(self, test_router, get_mock_github_api):
        mentions_seen = []

        @test_router.mention(username=re.compile(r".*"))
        def all_mentions_handler(event, *args, **kwargs):
            mention = kwargs.get("context")
            mentions_seen.append(mention.mention.username)

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@alice review @bob deploy @charlie test",
                    "user": {"login": "user"},
                },
                "issue": {"number": 1},
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert mentions_seen == ["alice", "bob", "charlie"]

    def test_combined_filters(self, test_router, get_mock_github_api):
        calls = []

        @test_router.mention(
            username=re.compile(r".*-bot"),
            pattern="deploy",
            scope=MentionScope.PR,
        )
        def restricted_deploy(event, *args, **kwargs):
            calls.append(kwargs)

        def make_event(body):
            return sansio.Event(
                {
                    "action": "created",
                    "comment": {"body": body, "user": {"login": "user"}},
                    "issue": {"number": 1, "pull_request": {"url": "..."}},
                    "repository": {"owner": {"login": "owner"}, "name": "repo"},
                },
                event="issue_comment",
                delivery_id="1",
            )

        # All conditions met
        event1 = make_event("@deploy-bot deploy now")
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event1, mock_gh)

        assert len(calls) == 1

        # Wrong username pattern
        calls.clear()
        event2 = make_event("@bot deploy now")
        test_router.dispatch(event2, mock_gh)

        assert len(calls) == 0

        # Wrong pattern
        calls.clear()
        event3 = make_event("@deploy-bot help")
        test_router.dispatch(event3, mock_gh)

        assert len(calls) == 0

        # Wrong scope (issue instead of PR)
        calls.clear()
        event4 = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@deploy-bot deploy now",
                    "user": {"login": "user"},
                },
                "issue": {"number": 1},  # No pull_request field
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        test_router.dispatch(event4, mock_gh)

        assert len(calls) == 0

    def test_multiple_decorators_different_patterns(
        self, test_router, get_mock_github_api
    ):
        patterns_matched = []

        @test_router.mention(pattern=re.compile(r"deploy"))
        @test_router.mention(pattern=re.compile(r"ship"))
        @test_router.mention(pattern=re.compile(r"release"))
        def deploy_handler(event, *args, **kwargs):
            mention = kwargs.get("context")
            patterns_matched.append(mention.mention.text.split()[0])

        event = sansio.Event(
            {
                "action": "created",
                "comment": {"body": "@bot ship it", "user": {"login": "user"}},
                "issue": {"number": 1},
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert patterns_matched == ["ship"]

    def test_question_pattern(self, test_router, get_mock_github_api):
        questions_received = []

        @test_router.mention(pattern=re.compile(r".*\?$"))
        def question_handler(event, *args, **kwargs):
            mention = kwargs.get("context")
            questions_received.append(mention.mention.text)

        event = sansio.Event(
            {
                "action": "created",
                "comment": {
                    "body": "@bot what is the status?",
                    "user": {"login": "user"},
                },
                "issue": {"number": 1},
                "repository": {"owner": {"login": "owner"}, "name": "repo"},
            },
            event="issue_comment",
            delivery_id="1",
        )
        mock_gh = get_mock_github_api({})
        test_router.dispatch(event, mock_gh)

        assert questions_received == ["what is the status?"]

        # Non-question should not match
        questions_received.clear()
        event.data["comment"]["body"] = "@bot please help"
        test_router.dispatch(event, mock_gh)
        assert questions_received == []
