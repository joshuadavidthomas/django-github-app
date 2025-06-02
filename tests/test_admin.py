from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from django_github_app.admin import EventLogModelAdmin
from django_github_app.models import EventLog

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(
        username="admin", email="admin@test.com", password="adminpass"
    )


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def eventlog_admin(admin_site):
    return EventLogModelAdmin(EventLog, admin_site)


@pytest.fixture
def factory():
    return RequestFactory()


class TestEventLogModelAdmin:
    def test_cleanup_url_exists(self, client, admin_user):
        client.login(username="admin", password="adminpass")
        response = client.get(reverse("admin:django_github_app_eventlog_changelist"))

        assert response.status_code == 200
        # Check that the cleanup URL is in the rendered HTML
        cleanup_url = reverse("admin:django_github_app_eventlog_cleanup")
        assert cleanup_url.encode() in response.content

    def test_cleanup_view_get(self, factory, admin_user, eventlog_admin):
        request = factory.get("/admin/django_github_app/eventlog/cleanup/")
        request.user = admin_user
        response = eventlog_admin.cleanup_view(request)

        assert response.status_code == 200
        assert b"Clean up event logs" in response.content
        assert b"Days to keep" in response.content

    def test_cleanup_view_post_shows_confirmation(self, client, admin_user, baker):
        # Create some test events
        now = timezone.now()
        baker.make(EventLog, _quantity=3, received_at=now - datetime.timedelta(days=10))
        baker.make(EventLog, _quantity=2, received_at=now - datetime.timedelta(days=2))

        client.login(username="admin", password="adminpass")
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"days_to_keep": "5"},
        )

        assert response.status_code == 200
        assert b"You are about to delete 3 event logs" in response.content
        assert b"Yes, I" in response.content and b"m sure" in response.content

    @patch("django_github_app.models.EventLog.objects.cleanup_events")
    def test_cleanup_view_confirm_deletion(self, mock_cleanup, client, admin_user):
        mock_cleanup.return_value = (5, {"django_github_app.EventLog": 5})

        client.login(username="admin", password="adminpass")
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"post": "yes", "days_to_keep": "3"},
        )

        assert response.status_code == 302
        assert response.url == reverse("admin:django_github_app_eventlog_changelist")
        mock_cleanup.assert_called_once_with(3)

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Successfully deleted 5 events older than 3 days" in str(messages[0])

    @patch("django_github_app.models.EventLog.objects.cleanup_events")
    def test_cleanup_view_confirm_deletion_singular_day(
        self, mock_cleanup, client, admin_user
    ):
        mock_cleanup.return_value = (2, {"django_github_app.EventLog": 2})

        client.login(username="admin", password="adminpass")
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"post": "yes", "days_to_keep": "1"},
        )

        assert response.status_code == 302

        # Check success message uses singular "day" and plural "events"
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Successfully deleted 2 events older than 1 day" in str(messages[0])

    @patch("django_github_app.models.EventLog.objects.cleanup_events")
    def test_cleanup_view_confirm_deletion_zero_events(
        self, mock_cleanup, client, admin_user
    ):
        mock_cleanup.return_value = (0, {})

        client.login(username="admin", password="adminpass")
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"post": "yes", "days_to_keep": "7"},
        )

        assert response.status_code == 302

        # Check success message uses plural "events" for zero
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Successfully deleted 0 events older than 7 days" in str(messages[0])

    def test_cleanup_view_integration(self, client, admin_user, baker):
        now = timezone.now()

        # Create test EventLog entries using baker
        old_event = baker.make(
            EventLog,
            event="push",
            payload={"action": "created"},
            received_at=now - datetime.timedelta(days=10),
        )
        recent_event = baker.make(
            EventLog,
            event="pull_request",
            payload={"action": "opened"},
            received_at=now - datetime.timedelta(days=2),
        )

        client.login(username="admin", password="adminpass")

        # Test GET request
        response = client.get(reverse("admin:django_github_app_eventlog_cleanup"))
        assert response.status_code == 200

        # Test POST request - Step 1: Show confirmation
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"days_to_keep": "5"},
        )
        assert response.status_code == 200
        assert b"You are about to delete 1 event log" in response.content

        # Test POST request - Step 2: Confirm deletion
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"post": "yes", "days_to_keep": "5"},
        )
        assert response.status_code == 302

        # Check that old event was deleted and recent event remains
        assert not EventLog.objects.filter(id=old_event.id).exists()
        assert EventLog.objects.filter(id=recent_event.id).exists()

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Successfully deleted 1 event older than 5 days" in str(messages[0])
