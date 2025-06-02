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
    def test_cleanup_url_in_changelist_context(
        self, factory, admin_user, eventlog_admin
    ):
        request = factory.get("/admin/django_github_app/eventlog/")
        request.user = admin_user
        response = eventlog_admin.changelist_view(request)

        assert "cleanup_url" in response.context_data
        assert response.context_data["cleanup_url"] == reverse(
            "admin:django_github_app_eventlog_cleanup"
        )

    def test_cleanup_view_get(self, factory, admin_user, eventlog_admin):
        request = factory.get("/admin/django_github_app/eventlog/cleanup/")
        request.user = admin_user
        response = eventlog_admin.cleanup_view(request)

        assert response.status_code == 200
        assert b"Clean up Events" in response.content
        assert b"Days to keep events" in response.content

    @patch("django_github_app.models.EventLog.objects.cleanup_events")
    def test_cleanup_view_post(self, mock_cleanup, client, admin_user):
        mock_cleanup.return_value = (5, {"django_github_app.EventLog": 5})

        client.login(username="admin", password="adminpass")
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"days_to_keep": "3"},
        )

        assert response.status_code == 302
        assert response.url == reverse("admin:django_github_app_eventlog_changelist")
        mock_cleanup.assert_called_once_with(3)

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Successfully deleted 5 event(s)" in str(messages[0])

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

        # Test POST request
        response = client.post(
            reverse("admin:django_github_app_eventlog_cleanup"),
            {"days_to_keep": "5"},
        )
        assert response.status_code == 302

        # Check that old event was deleted and recent event remains
        assert not EventLog.objects.filter(id=old_event.id).exists()
        assert EventLog.objects.filter(id=recent_event.id).exists()

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert "Successfully deleted 1 event(s)" in str(messages[0])
