from __future__ import annotations

import pytest
from django.http import HttpRequest
from django.http import JsonResponse

from django_github_app.github import SyncGitHubAPI
from django_github_app.routing import GitHubRouter
from django_github_app.views import BaseWebhookView

pytestmark = pytest.mark.django_db


class TestView(BaseWebhookView[SyncGitHubAPI]):
    github_api_class = SyncGitHubAPI

    def post(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({})


class BrokenTestView(BaseWebhookView[SyncGitHubAPI]):
    github_api_class = SyncGitHubAPI

    # Intentionally break the singleton pattern to demonstrate memory issue
    @property
    def router(self) -> GitHubRouter:
        # Always create a new router (simulating the original issue)
        return GitHubRouter(*GitHubRouter.routers)

    def post(self, request: HttpRequest) -> JsonResponse:
        return JsonResponse({})


class TestGitHubRouter:
    def test_router_single_instance(self):
        """Test that router is instantiated only once per view class."""
        # Reset the router
        TestView._router = None

        # Create multiple views
        view1 = TestView()
        view2 = TestView()

        # Get router from both instances
        router1 = view1.router
        router2 = view2.router

        # Verify they are the same object
        assert router1 is router2

        # Verify subsequent calls return the same instance
        assert view1.router is router1
        assert view2.router is router2

    def test_router_multiple_instances_without_fix(self):
        """Test demonstrates that without the fix, each view gets a new router instance.

        This test shows that the problem that was fixed (creating a new router on each access)
        would result in multiple router instances. This test validates the behavior without
        using memray to measure memory usage.
        """
        # Create views with the broken implementation that creates new routers
        views = []
        routers = []

        # Create just a few views - enough to demonstrate the issue
        for _ in range(5):
            view = BrokenTestView()
            # Get a router reference from each view
            router = view.router
            views.append(view)
            routers.append(router)

        # Ensure we have the expected number of views
        assert len(views) == 5

        # Verify that without the fix, each view gets a unique router instance
        unique_router_count = len(set(id(r) for r in routers))
        assert unique_router_count == 5, (
            f"Expected 5 unique routers, got {unique_router_count}"
        )

    def test_fix_prevents_duplicate_routers(self):
        """Test that the fix prevents duplication of routers even when accessed multiple times.

        This test simulates accessing the router multiple times from different views,
        which is what happens in a high-traffic application with many requests.
        """
        # Reset the router
        TestView._router = None

        # Create a reference to the first router
        view1 = TestView()
        first_router = view1.router

        # Track the number of unique router instances
        router_ids = {id(first_router)}

        # Simulate multiple requests by creating views and accessing their router repeatedly
        for _ in range(100):
            view = TestView()

            # Access the router multiple times (simulating multiple uses per request)
            for _ in range(10):
                router = view.router
                router_ids.add(id(router))

        # With the fix, we should have exactly ONE router instance despite
        # creating it 100 views x 10 accesses = 1000 times
        assert len(router_ids) == 1, (
            f"Expected 1 unique router ID, got {len(router_ids)}"
        )

    @pytest.mark.limit_memory("10MB")
    def test_router_memory_with_fix(self):
        """Test memory usage with the fix in place.

        This test creates a massive number of views with the fixed implementation,
        which should use minimal memory since all views share the same router.
        """
        # Reset the router
        TestView._router = None

        # Create an extremely large number of views to really stress test the system
        view_count = 5000  # Still a lot of views but not so many that it hangs

        # Store all views in memory to prevent garbage collection
        # This gives us a more realistic picture of memory usage
        views = []

        # Create many views and access their routers
        for i in range(view_count):
            view = TestView()
            # Access the router property to trigger creation if not already created
            router = view.router

            # Store view in list to prevent garbage collection
            views.append(view)

            # Only store a reference to the first router to compare later
            if i == 0:
                first_router = router

        # Ensure we created the expected number of views
        assert len(views) == view_count

        # Verify all views share the same router instance
        for view in views:
            assert view.router is first_router
