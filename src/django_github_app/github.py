from __future__ import annotations

import asyncio
from collections.abc import Generator
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Any
from urllib.parse import urlencode

import cachetools
import gidgethub
import httpx
from asgiref.sync import async_to_sync
from gidgethub import abc as gh_abc
from gidgethub import sansio
from uritemplate import variable

from ._sync import async_to_sync_method
from ._typing import override

cache: cachetools.LRUCache[Any, Any] = cachetools.LRUCache(maxsize=500)
# need to create an ssl_context in the main thread, see:
# - https://github.com/pallets/flask/discussions/5387#discussioncomment-10835348
# - https://github.com/indygreg/python-build-standalone/issues/207
# - https://github.com/jsirois/pex/blob/b88855f72f46b29709e8a514b6a13432a08a097d/pex/fetcher.py#L68-L118
ssl_context = httpx.create_ssl_context()


class AsyncGitHubAPI(gh_abc.GitHubAPI):
    def __init__(
        self,
        *args: Any,
        installation_id: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.installation_id = installation_id
        self._client = httpx.AsyncClient(verify=ssl_context)
        super().__init__(*args, cache=cache, **kwargs)

    async def __aenter__(self) -> AsyncGitHubAPI:
        from .models import Installation

        if self.installation_id:
            try:
                installation = await Installation.objects.aget(
                    installation_id=self.installation_id
                )
                self.oauth_token = await installation.aget_access_token(self)
            except (Installation.DoesNotExist, gidgethub.BadRequest):
                self.oauth_token = None
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self._client.aclose()

    @override
    async def _request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> tuple[int, httpx.Headers, bytes]:
        response = await self._client.request(
            method, url, headers=dict(headers), content=body
        )
        return response.status_code, response.headers, response.content

    @override
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class SyncGitHubAPI(AsyncGitHubAPI):
    __enter__ = async_to_sync_method(AsyncGitHubAPI.__aenter__)
    __exit__ = async_to_sync_method(AsyncGitHubAPI.__aexit__)
    getitem = async_to_sync_method(AsyncGitHubAPI.getitem)
    getstatus = async_to_sync_method(AsyncGitHubAPI.getstatus)  # type: ignore[arg-type]
    post = async_to_sync_method(AsyncGitHubAPI.post)
    patch = async_to_sync_method(AsyncGitHubAPI.patch)
    put = async_to_sync_method(AsyncGitHubAPI.put)
    delete = async_to_sync_method(AsyncGitHubAPI.delete)  # type: ignore[arg-type]
    graphql = async_to_sync_method(AsyncGitHubAPI.graphql)

    @override  # type: ignore[override]
    def sleep(self, seconds: float) -> None:
        raise NotImplementedError(
            "sleep() is not supported in SyncGitHubAPI due to abstractmethod"
            "gidgethub.abc.GitHubAPI.sleep's async requirements. "
            "Use time.sleep() directly instead."
        )

    @override
    def getiter(  # type: ignore[override]
        self,
        url: str,
        url_vars: variable.VariableValueDict | None = {},
        *,
        accept: str = sansio.accept_format(),
        jwt: str | None = None,
        oauth_token: str | None = None,
        extra_headers: dict[str, str] | None = None,
        iterable_key: str | None = gh_abc.ITERABLE_KEY,
    ) -> Generator[Any, None, None]:
        data, more, _ = async_to_sync(super()._make_request)(
            "GET",
            url,
            url_vars,
            b"",
            accept,
            jwt=jwt,
            oauth_token=oauth_token,
            extra_headers=extra_headers,
        )

        if isinstance(data, dict) and iterable_key in data:
            data = data[iterable_key]

        yield from data

        if more:
            yield from self.getiter(
                more,
                url_vars,
                accept=accept,
                jwt=jwt,
                oauth_token=oauth_token,
                iterable_key=iterable_key,
                extra_headers=extra_headers,
            )


class GitHubAPIEndpoint(Enum):
    INSTALLATION_REPOS = "/installation/repositories"
    ORG_APP_INSTALLATION = "/orgs/{org}/installation"
    REPO_ISSUES = "/repos/{owner}/{repo}/issues"
    USER_APP_INSTALLATION = "/users/{username}/installation"


@dataclass(frozen=True, slots=True)
class GitHubAPIUrl:
    endpoint: GitHubAPIEndpoint | str
    url_vars: variable.VariableValueDict | None = None
    params: dict[str, Any] | None = None

    @property
    def full_url(self):
        endpoint = (
            self.endpoint if isinstance(self.endpoint, str) else self.endpoint.value
        )
        url = [sansio.format_url(endpoint, self.url_vars)]
        if self.params:
            url.append(f"?{urlencode(self.params)}")
        return "".join(url)
