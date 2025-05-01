from __future__ import annotations

import pytest
from django.http import HttpRequest
from django.http import JsonResponse

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


class FixedTestView(BaseWebhookView[SyncGitHubAPI]):
    github_api_class = SyncGitHubAPI

    def post(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({})


class BrokenTestView(BaseWebhookView[SyncGitHubAPI]):
    github_api_class = SyncGitHubAPI

    @property
    def router(self) -> GitHubRouter:
        # Always create a new router (simulating issue #73)
        return GitHubRouter(*GitHubRouter.routers)

    def post(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({})


class TestGitHubRouter:
    def test_router_single_instance(self):
        view1 = FixedTestView()
        view2 = FixedTestView()

        router1 = view1.router
        router2 = view2.router

        assert router1 is router2
        assert view1.router is router1
        assert view2.router is router2

    def test_duplicate_routers_without_module_level_router(self):
        view_count = 5

        views = []
        routers = []

        for _ in range(view_count):
            view = BrokenTestView()
            views.append(view)
            routers.append(view.router)

        assert len(views) == view_count

        unique_router_count = len(set(id(r) for r in routers))
        assert unique_router_count == view_count

    def test_no_duplicate_routers(self):
        router_ids = set()

        for _ in range(100):
            view = FixedTestView()

            # really goose it up with adding duplicate routers
            for _ in range(10):
                router_ids.add(id(view.router))

        # we should have exactly ONE router instance despite
        # creating it 100 views x 10 accesses = 1000 times
        assert len(router_ids) == 1

    @pytest.mark.limit_memory("2.5MB")
    def test_router_memory_stress_test(self):
        view_count = 50000

        views = []

        for _ in range(view_count):
            view = FixedTestView()
            views.append(view)

        assert len(views) == view_count
        assert all(view.router is views[0].router for view in views)
