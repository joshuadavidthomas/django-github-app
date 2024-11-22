from __future__ import annotations

import pytest
from django.views.generic import View
from gidgethub import sansio

from django_github_app.routing import GitHubRouter
from django_github_app.views import AsyncWebhookView
from django_github_app.views import SyncWebhookView

from .utils import seq


@pytest.fixture
def test_router():
    GitHubRouter._reset()
    router = GitHubRouter()
    yield router
    GitHubRouter._reset()


class TestGitHubRouter:
    @pytest.mark.parametrize(
        "urls",
        [
            [SyncWebhookView],
            [AsyncWebhookView],
            [View],
            [],
        ],
    )
    def test_library_handlers_loaded(self, urls, test_router, urlpatterns):
        assert test_router._library_handlers_loaded is False
        event = sansio.Event(
            data={"action": "created"}, event="installation", delivery_id=seq.next()
        )

        with urlpatterns(urls):
            test_router._load_library_handlers()
            handlers = test_router.fetch(event)

        assert test_router._library_handlers_loaded is True
        assert len(handlers) > 0
