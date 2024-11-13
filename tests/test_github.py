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
    def test_not_implemented_error(self):
        with pytest.raises(NotImplementedError):
            SyncGitHubAPI("not-implemented")


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
