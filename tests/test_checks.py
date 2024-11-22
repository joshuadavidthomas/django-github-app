from __future__ import annotations

from django.core.checks import Error
from django.views.generic import View

from django_github_app.checks import check_webhook_views
from django_github_app.checks import get_webhook_views
from django_github_app.views import AsyncWebhookView
from django_github_app.views import SyncWebhookView


class TestProjectWebhookViews:
    def test_get_async(self, urlpatterns):
        with urlpatterns([AsyncWebhookView]):
            views = get_webhook_views()

        assert len(views) == 1
        assert views[0] == AsyncWebhookView

    def test_get_sync(self, urlpatterns):
        with urlpatterns([SyncWebhookView]):
            views = get_webhook_views()

        assert len(views) == 1
        assert views[0] == SyncWebhookView

    def test_get_both(self, urlpatterns):
        with urlpatterns([AsyncWebhookView, SyncWebhookView]):
            views = get_webhook_views()

        assert len(views) == 2
        assert AsyncWebhookView in views
        assert SyncWebhookView in views

    def test_get_normal_view(self, urlpatterns):
        with urlpatterns([View]):
            views = get_webhook_views()

        assert len(views) == 0

    def test_get_none(self, urlpatterns):
        with urlpatterns([]):
            views = get_webhook_views()

        assert len(views) == 0


class TestCheckWebhookViews:
    def test_async(self, urlpatterns):
        with urlpatterns([AsyncWebhookView]):
            errors = check_webhook_views(None)

        assert not errors

    def test_sync(self, urlpatterns):
        with urlpatterns([SyncWebhookView]):
            errors = check_webhook_views(None)

        assert not errors

    def test_async_multiple(self, urlpatterns):
        with urlpatterns([AsyncWebhookView, AsyncWebhookView]):
            errors = check_webhook_views(None)

        assert not errors

    def test_sync_multiple(self, urlpatterns):
        with urlpatterns([SyncWebhookView, SyncWebhookView]):
            errors = check_webhook_views(None)

        assert not errors

    def test_mixed_error(self, urlpatterns):
        with urlpatterns([AsyncWebhookView, SyncWebhookView]):
            errors = check_webhook_views(None)

        assert len(errors) == 1

        error = errors[0]

        assert isinstance(error, Error)
        assert error.id == "django_github_app.E001"
        assert "Multiple webhook view types detected" in error.msg
        assert "Use either AsyncWebhookView or SyncWebhookView" in error.hint

    def test_normal_view(self, urlpatterns):
        with urlpatterns([View]):
            errors = check_webhook_views(None)

        assert not errors

    def test_none(self, urlpatterns):
        with urlpatterns([]):
            errors = check_webhook_views(None)

        assert not errors
