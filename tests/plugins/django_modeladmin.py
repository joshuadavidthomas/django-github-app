# pattern adapted from https://adamj.eu/tech/2023/03/17/django-parameterized-tests-model-admin-classes/
from __future__ import annotations

from http import HTTPStatus

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import override_settings
from django.urls import clear_url_caches
from django.urls import path
from django.urls import reverse


class TestAdminSite(AdminSite):
    def __init__(self):
        super().__init__(name="testadmin")


admin_site = TestAdminSite()


@pytest.fixture(scope="session")
def test_admin_site():
    return admin_site


@pytest.fixture(autouse=True)
def setup_admin_urls():
    """Set up admin URLs for testing."""
    urlpatterns = [
        path("admin/", admin_site.urls),
    ]

    clear_url_caches()

    with override_settings(
        ROOT_URLCONF=type(
            "urls",
            (),
            {"urlpatterns": urlpatterns},
        ),
    ):
        yield

    clear_url_caches()


@pytest.fixture
def admin_client(django_user_model, client):
    """Create and return an admin client."""
    admin_user = django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="test"
    )
    client.force_login(admin_user)
    return client


@pytest.mark.parametrize(
    "model,model_admin",
    [
        pytest.param(
            model,
            model_admin,
            id=f"{model._meta.app_label}_{model._meta.model_name}",
        )
        for model, model_admin in admin_site._registry.items()
    ],
)
@pytest.mark.django_db
class TestModelAdmins:
    """Test suite for Django model admins."""

    def test_changelist(self, admin_client, model, model_admin):
        """Test the changelist view for each model admin."""
        url = reverse(
            f"{admin_site.name}:{model._meta.app_label}_{model._meta.model_name}_changelist"
        )

        response = admin_client.get(url, {"q": "example.com"})

        assert response.status_code == HTTPStatus.OK

    def test_add(self, admin_client, model, model_admin):
        """Test the add view for each model admin."""
        url = reverse(
            f"{admin_site.name}:{model._meta.app_label}_{model._meta.model_name}_add"
        )

        response = admin_client.get(url)

        assert response.status_code in (HTTPStatus.OK, HTTPStatus.FORBIDDEN)
