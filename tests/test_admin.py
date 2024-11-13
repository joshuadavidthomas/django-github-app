# pattern adapted from https://adamj.eu/tech/2023/03/17/django-parameterized-tests-model-admin-classes/
from __future__ import annotations

from http import HTTPStatus

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import override_settings
from django.urls import clear_url_caches
from django.urls import path
from django.urls import reverse

from django_github_app.admin import EventLogModelAdmin
from django_github_app.admin import InstallationModelAdmin
from django_github_app.admin import RepositoryModelAdmin
from django_github_app.models import EventLog
from django_github_app.models import Installation
from django_github_app.models import Repository


class TestAdminSite(AdminSite):
    def __init__(self):
        super().__init__(name="testadmin")


admin_site = TestAdminSite()
admin_site.register(EventLog, EventLogModelAdmin)
admin_site.register(Installation, InstallationModelAdmin)
admin_site.register(Repository, RepositoryModelAdmin)


@pytest.fixture(autouse=True)
def setup():
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
            id=f"{str(model_admin).replace('.', '_')}",
        )
        for model, model_admin in admin_site._registry.items()
    ],
)
@pytest.mark.django_db
class TestModelAdmins:
    def test_changelist(self, admin_client, model, model_admin):
        url = reverse(
            f"{admin_site.name}:{model._meta.app_label}_{model._meta.model_name}_changelist"
        )

        response = admin_client.get(url, {"q": "example.com"})

        assert response.status_code == HTTPStatus.OK

    def test_add(self, admin_client, model, model_admin):
        url = reverse(
            f"{admin_site.name}:{model._meta.app_label}_{model._meta.model_name}_add"
        )

        response = admin_client.get(url)

        assert response.status_code in (HTTPStatus.OK, HTTPStatus.FORBIDDEN)
