from __future__ import annotations

import datetime
import hmac
import json
from http import HTTPStatus

import pytest
from asgiref.sync import sync_to_async
from django.core.exceptions import BadRequest
from django.http import JsonResponse
from django.utils import timezone
from gidgethub import sansio
from gidgethub.abc import GitHubAPI
from model_bakery import baker

from django_github_app.github import AsyncGitHubAPI
from django_github_app.github import SyncGitHubAPI
from django_github_app.models import EventLog
from django_github_app.views import AsyncWebhookView
from django_github_app.views import BaseWebhookView
from django_github_app.views import SyncWebhookView

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "webhook-secret"


@pytest.fixture(autouse=True)
def webhook_secret(override_app_settings):
    with override_app_settings(WEBHOOK_SECRET=WEBHOOK_SECRET):
        yield


@pytest.fixture
def webhook_request(rf):
    def _make_request(
        event_type: str | None = "push",
        body: dict[str, str] | None = None,
        delivery_id: int = 1234,
        secret: str = WEBHOOK_SECRET,
    ):
        if body is None:
            body = {}

        body_json = json.dumps(body).encode("UTF-8")
        hmac_obj = hmac.new(
            secret.encode("UTF-8"),
            msg=body_json,
            digestmod="sha256",
        )
        signature = f"sha256={hmac_obj.hexdigest()}"

        headers = {
            "HTTP_X_HUB_SIGNATURE_256": signature,
            "HTTP_X_GITHUB_DELIVERY": delivery_id,
        }
        if event_type is not None:
            headers["HTTP_X_GITHUB_EVENT"] = event_type

        request = rf.post(
            "/webhook/",
            data=body_json,
            content_type="application/json",
            **headers,
        )
        return request

    return _make_request


@pytest.fixture
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


@pytest.fixture
def aregister_webhook_event(test_router):
    def _make_handler(event_type, should_fail=False):
        data = {}

        @test_router.event(event_type)
        async def handle_event(event, gh):
            if should_fail:
                pytest.fail("Should not be called")
            data["event"] = event
            data["gh"] = gh

        return data

    return _make_handler


@pytest.fixture
def register_webhook_event(test_router):
    def _make_handler(event_type, should_fail=False):
        data = {}

        @test_router.event(event_type)
        def handle_event(event, gh):
            if should_fail:
                pytest.fail("Should not be called")
            data["event"] = event
            data["gh"] = gh

        return data

    return _make_handler


class WebhookView(BaseWebhookView[GitHubAPI]):
    github_api_class = GitHubAPI

    def post(self, request):
        return JsonResponse({})


class TestBaseWebhookView:
    def test_get_event(self, webhook_request):
        event_type = "installation"
        body = {"foo": "bar"}
        delivery_id = 4321

        request = webhook_request(event_type, body, delivery_id)
        view = WebhookView()
        event = view.get_event(request)

        assert isinstance(event, sansio.Event)
        assert event.event == event_type
        assert event.data == body
        assert event.delivery_id == delivery_id

    @pytest.mark.parametrize(
        "github_api_class",
        [AsyncGitHubAPI, SyncGitHubAPI],
    )
    def test_get_github_api(self, github_api_class, installation):
        view = WebhookView()
        view.github_api_class = github_api_class

        gh = view.get_github_api(installation)

        assert isinstance(gh, github_api_class)
        assert gh.installation_id == installation.installation_id

    def test_get_response(self, webhook_request):
        view = WebhookView()

        response = view.get_response(baker.make("django_github_app.EventLog"))

        assert isinstance(response, JsonResponse)
        assert response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
class TestAsyncWebhookView:
    async def test_post(self, webhook_request):
        request = webhook_request()
        view = AsyncWebhookView()

        response = await view.post(request)

        assert isinstance(response, JsonResponse)
        assert response.status_code == HTTPStatus.OK

    async def test_csrf_exempt(self, webhook_request):
        request = webhook_request()
        view = AsyncWebhookView()

        response = await view.post(request)

        assert response.status_code != HTTPStatus.FORBIDDEN

    async def test_event_log_created(self, webhook_request, aregister_webhook_event):
        aregister_webhook_event("push")
        request = webhook_request(event_type="push")
        view = AsyncWebhookView()

        response = await view.post(request)

        event_id = json.loads(response.content)["event_id"]
        assert await EventLog.objects.filter(id=event_id).acount() == 1

    async def test_event_log_cleanup(self, webhook_request):
        request = webhook_request()
        view = AsyncWebhookView()

        event = await sync_to_async(baker.make)(
            "django_github_app.EventLog",
            received_at=timezone.now() - datetime.timedelta(days=8),
        )
        assert await EventLog.objects.filter(id=event.id).acount() == 1

        await view.post(request)

        assert await EventLog.objects.filter(id=event.id).acount() == 0

    async def test_invalid_webhook_secret(self, webhook_request):
        request = webhook_request(secret="invalid-secret")
        view = AsyncWebhookView()

        with pytest.raises(BadRequest):
            await view.post(request)

    async def test_missing_event(self, webhook_request):
        request = webhook_request(event_type=None)
        view = AsyncWebhookView()

        with pytest.raises(BadRequest):
            await view.post(request)

    async def test_router_dispatch(self, aregister_webhook_event, webhook_request):
        webhook_data = aregister_webhook_event("push")
        request = webhook_request(
            event_type="push",
            body={"action": "created", "repository": {"full_name": "test/repo"}},
        )
        view = AsyncWebhookView()

        response = await view.post(request)

        assert response.status_code == HTTPStatus.OK
        assert webhook_data["event"].event == "push"
        assert webhook_data["event"].data["repository"]["full_name"] == "test/repo"
        assert isinstance(webhook_data["gh"], AsyncGitHubAPI)

    async def test_router_dispatch_unhandled_event(
        self, monkeypatch, aregister_webhook_event, override_app_settings, create_event
    ):
        with override_app_settings(LOG_ALL_EVENTS=False):
            aregister_webhook_event("push", should_fail=True)
            view = AsyncWebhookView()

            event = create_event("issues", action="opened", delivery_id="12345")

            monkeypatch.setattr(view, "get_event", lambda request: event)

            response = await view.post(None)

            assert response.status_code == HTTPStatus.OK
            assert json.loads(response.content) == {"message": "ok"}

    async def test_unhandled_event_log_creation_with_log_all(
        self, monkeypatch, aregister_webhook_event, override_app_settings, create_event
    ):
        with override_app_settings(LOG_ALL_EVENTS=True):
            aregister_webhook_event("push", should_fail=True)
            view = AsyncWebhookView()

            event = create_event("issues", action="opened", delivery_id="12345")

            monkeypatch.setattr(view, "get_event", lambda request: event)

            count_before = await EventLog.objects.acount()

            await view.post(None)

            count_after = await EventLog.objects.acount()
            assert count_after - count_before == 1

    async def test_unhandled_event_log_creation_without_log_all(
        self, monkeypatch, aregister_webhook_event, override_app_settings, create_event
    ):
        with override_app_settings(LOG_ALL_EVENTS=False):
            aregister_webhook_event("push", should_fail=True)
            view = AsyncWebhookView()

            event = create_event("issues", action="opened", delivery_id="12345")

            monkeypatch.setattr(view, "get_event", lambda request: event)

            count_before = await EventLog.objects.acount()

            await view.post(None)

            count_after = await EventLog.objects.acount()
            assert count_after - count_before == 0


class TestSyncWebhookView:
    def test_post(self, webhook_request):
        request = webhook_request()
        view = SyncWebhookView()

        response = view.post(request)

        assert isinstance(response, JsonResponse)
        assert response.status_code == HTTPStatus.OK

    def test_csrf_exempt(self, webhook_request):
        request = webhook_request()
        view = SyncWebhookView()

        response = view.post(request)

        assert response.status_code != HTTPStatus.FORBIDDEN

    def test_event_log_created(self, webhook_request, register_webhook_event):
        register_webhook_event("push")
        request = webhook_request(event_type="push")
        view = SyncWebhookView()

        response = view.post(request)

        event_id = json.loads(response.content)["event_id"]
        assert EventLog.objects.filter(id=event_id).count() == 1

    def test_event_log_cleanup(self, webhook_request):
        request = webhook_request()
        view = SyncWebhookView()

        event = baker.make(
            "django_github_app.EventLog",
            received_at=timezone.now() - datetime.timedelta(days=8),
        )
        assert EventLog.objects.filter(id=event.id).count() == 1

        view.post(request)

        assert EventLog.objects.filter(id=event.id).count() == 0

    def test_router_dispatch(self, register_webhook_event, webhook_request):
        webhook_data = register_webhook_event("push")
        request = webhook_request(
            event_type="push",
            body={"action": "created", "repository": {"full_name": "test/repo"}},
        )
        view = SyncWebhookView()

        response = view.post(request)

        assert response.status_code == HTTPStatus.OK
        assert webhook_data["event"].event == "push"
        assert webhook_data["event"].data["repository"]["full_name"] == "test/repo"
        assert isinstance(webhook_data["gh"], SyncGitHubAPI)

    def test_router_dispatch_unhandled_event(
        self, monkeypatch, register_webhook_event, override_app_settings, create_event
    ):
        with override_app_settings(LOG_ALL_EVENTS=False):
            register_webhook_event("push", should_fail=True)
            view = SyncWebhookView()

            event = create_event("issues", action="opened", delivery_id="12345")

            monkeypatch.setattr(view, "get_event", lambda request: event)

            response = view.post(None)

            assert response.status_code == HTTPStatus.OK
            assert json.loads(response.content) == {"message": "ok"}

    def test_unhandled_event_log_creation_with_log_all(
        self, monkeypatch, register_webhook_event, override_app_settings, create_event
    ):
        with override_app_settings(LOG_ALL_EVENTS=True):
            register_webhook_event("push", should_fail=True)
            view = SyncWebhookView()

            event = create_event("issues", action="opened", delivery_id="12345")

            monkeypatch.setattr(view, "get_event", lambda request: event)

            count_before = EventLog.objects.count()

            view.post(None)

            count_after = EventLog.objects.count()
            assert count_after - count_before == 1

    def test_unhandled_event_log_creation_without_log_all(
        self, monkeypatch, register_webhook_event, override_app_settings, create_event
    ):
        with override_app_settings(LOG_ALL_EVENTS=False):
            register_webhook_event("push", should_fail=True)
            view = SyncWebhookView()

            event = create_event("issues", action="opened", delivery_id="12345")

            monkeypatch.setattr(view, "get_event", lambda request: event)

            count_before = EventLog.objects.count()

            view.post(None)

            count_after = EventLog.objects.count()
            assert count_after - count_before == 0
