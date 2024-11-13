from __future__ import annotations

import logging

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from model_bakery import baker

from .settings import DEFAULT_SETTINGS
from .utils import seq

pytest_plugins = []


def pytest_configure(config):
    logging.disable(logging.CRITICAL)

    settings.configure(**DEFAULT_SETTINGS, **TEST_SETTINGS)


TEST_SETTINGS = {
    "MIDDLEWARE": [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
    "INSTALLED_APPS": [
        "django_github_app",
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
    ],
    "ROOT_URLCONF": "",
    "TEMPLATES": [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.debug",
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
            },
        }
    ],
}


@pytest.fixture
def id_sequence_start():
    return 1000


@pytest.fixture
def installation_id(id_sequence_start):
    return seq(id_sequence_start)


@pytest.fixture
def installation_id_iter(id_sequence_start):
    return seq.iter(id_sequence_start)


@pytest.fixture
def repository_id(id_sequence_start):
    return seq(id_sequence_start)


@pytest.fixture
def repository_id_iter(id_sequence_start):
    return seq.iter(id_sequence_start)


@pytest.fixture
def installation(installation_id):
    return baker.make("django_github_app.Installation", installation_id=installation_id)


@pytest.fixture
async def ainstallation(installation_id):
    return await sync_to_async(baker.make)(
        "django_github_app.Installation", installation_id=installation_id
    )
