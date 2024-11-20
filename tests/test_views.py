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
from django_github_app.routing import GitHubRouter
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

        hmac_obj = hmac.new(
            secret.encode("UTF-8"),
            msg=json.dumps(body).encode("UTF-8"),
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
            data=body,
            content_type="application/json",
            **headers,
        )
        return request

    return _make_request


@pytest.fixture
def test_router():
    router = GitHubRouter()
    yield router
    GitHubRouter._routers.remove(router.router)


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

    async def test_event_log_created(self, webhook_request):
        request = webhook_request()
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

    async def test_router_dispatch(self, test_router, webhook_request):
        called_with = {}

        @test_router.event("push")
        async def handle_push(event, gh):
            called_with["event"] = event
            called_with["gh"] = gh

        request = webhook_request(
            event_type="push",
            body={"action": "created", "repository": {"full_name": "test/repo"}},
        )
        view = AsyncWebhookView()

        response = await view.post(request)

        assert response.status_code == HTTPStatus.OK
        assert called_with["event"].event == "push"
        assert called_with["event"].data["repository"]["full_name"] == "test/repo"
        assert isinstance(called_with["gh"], AsyncGitHubAPI)

    async def test_router_dispatch_unhandled_event(self, test_router, webhook_request):
        @test_router.event("push")
        async def handle_push(event, gh):
            pytest.fail("Should not be called")

        request = webhook_request(event_type="issues", body={"action": "opened"})
        view = AsyncWebhookView()

        response = await view.post(request)

        assert response.status_code == HTTPStatus.OK


class TestSyncWebhookView:
    def test_not_implemented_error(self):
        with pytest.raises(NotImplementedError):
            SyncWebhookView()

    def test_post(self, webhook_request): ...
    def test_csrf_exempt(self, webhook_request): ...
    def test_event_log_created(self, webhook_request): ...
    def test_event_log_cleanup(self, webhook_request): ...
    def test_router_dispatch(self, test_router, webhook_request): ...
    def test_router_dispatch_unhandled_event(self, test_router, webhook_request): ...
