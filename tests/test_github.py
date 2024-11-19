from __future__ import annotations

import datetime

import pytest

from django_github_app.github import AsyncGitHubAPI
from django_github_app.github import GitHubAPIUrl
from django_github_app.github import SyncGitHubAPI
from django_github_app.models import Installation


@pytest.mark.asyncio
@pytest.mark.django_db
class TestAsyncGitHubAPI:
    async def test_request(self, httpx_mock):
        httpx_mock.add_response(json={"foo": "bar"})

        async with AsyncGitHubAPI("test") as gh:
            response = await gh.getitem("/foo")
            assert response == {"foo": "bar"}

    async def test_oauth_token(self, ainstallation, monkeypatch):
        async def mock_aget_access_token(*args, **kwargs):
            return "ABC123"

        monkeypatch.setattr(Installation, "aget_access_token", mock_aget_access_token)

        installation = await ainstallation

        async with AsyncGitHubAPI(
            "test", installation_id=installation.installation_id
        ) as gh:
            assert gh.oauth_token == "ABC123"

    async def test_oauth_token_installation_doesnotexist(self):
        async with AsyncGitHubAPI("test", installation_id=1234) as gh:
            assert gh.oauth_token is None

    async def test_oauth_token_no_installation_id(self):
        async with AsyncGitHubAPI("test") as gh:
            assert gh.oauth_token is None

    async def test_sleep(self):
        delay = 0.25
        start = datetime.datetime.now()

        async with AsyncGitHubAPI("test") as gh:
            await gh.sleep(delay)

        stop = datetime.datetime.now()
        assert (stop - start) > datetime.timedelta(seconds=delay)


class TestSyncGitHubAPI:
    def test_getitem(self, httpx_mock):
        httpx_mock.add_response(json={"foo": "bar"})

        with SyncGitHubAPI("test") as gh:
            response = gh.getitem("/foo")

        assert response == {"foo": "bar"}

    def test_getstatus(self, httpx_mock):
        httpx_mock.add_response(status_code=204)

        with SyncGitHubAPI("test") as gh:
            status = gh.getstatus("/foo")

        assert status == 204

    def test_post(self, httpx_mock):
        httpx_mock.add_response(json={"created": "success"})

        with SyncGitHubAPI("test") as gh:
            response = gh.post("/foo", data={"key": "value"})

        assert response == {"created": "success"}

    def test_patch(self, httpx_mock):
        httpx_mock.add_response(json={"updated": "success"})

        with SyncGitHubAPI("test") as gh:
            response = gh.patch("/foo", data={"key": "value"})

        assert response == {"updated": "success"}

    def test_put(self, httpx_mock):
        httpx_mock.add_response(json={"replaced": "success"})

        with SyncGitHubAPI("test") as gh:
            response = gh.put("/foo", data={"key": "value"})

        assert response == {"replaced": "success"}

    def test_delete(self, httpx_mock):
        httpx_mock.add_response(status_code=204)

        with SyncGitHubAPI("test") as gh:
            response = gh.delete("/foo")

        assert response is None  # assuming 204 returns None

    def test_graphql(self, httpx_mock):
        httpx_mock.add_response(json={"data": {"viewer": {"login": "octocat"}}})

        with SyncGitHubAPI("test") as gh:
            response = gh.graphql("""
                query {
                    viewer {
                        login
                    }
                }
            """)

        assert response == {"viewer": {"login": "octocat"}}

    def test_sleep(self):
        with pytest.raises(NotImplementedError):
            with SyncGitHubAPI("test") as gh:
                gh.sleep(1)

    def test_getiter(self, httpx_mock):
        httpx_mock.add_response(json={"items": [{"id": 1}, {"id": 2}]})

        with SyncGitHubAPI("test") as gh:
            items = list(gh.getiter("/foo"))

        assert items == [{"id": 1}, {"id": 2}]

    def test_getiter_pagination(self, httpx_mock):
        httpx_mock.add_response(
            json={"items": [{"id": 1}]},
            headers={"Link": '<next>; rel="next"'},
        )
        httpx_mock.add_response(json={"items": [{"id": 2}]})

        with SyncGitHubAPI("test") as gh:
            items = list(gh.getiter("/foo"))

        assert items == [{"id": 1}, {"id": 2}]
        assert len(httpx_mock.get_requests()) == 2

    def test_getiter_list(self, httpx_mock):
        httpx_mock.add_response(json=[{"id": 1}, {"id": 2}])

        with SyncGitHubAPI("test") as gh:
            items = list(gh.getiter("/foo"))

        assert items == [{"id": 1}, {"id": 2}]


class TestGitHubAPIUrl:
    @pytest.mark.parametrize(
        "endpoint,url_vars,params,expected",
        [
            (
                "/foo/{bar}",
                {"bar": "baz"},
                None,
                "https://api.github.com/foo/baz",
            ),
            (
                "/foo",
                None,
                {"bar": "baz"},
                "https://api.github.com/foo?bar=baz",
            ),
        ],
    )
    def test_full_url(self, endpoint, url_vars, params, expected):
        assert GitHubAPIUrl(endpoint, url_vars, params).full_url == expected
