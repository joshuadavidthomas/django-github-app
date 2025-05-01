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

    @pytest.mark.limit_memory("100KB")
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
