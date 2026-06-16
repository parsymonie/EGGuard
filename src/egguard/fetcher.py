"""HTTP fetching of UT1 category tarballs.

Wraps :mod:`requests` with conditional-request support (ETag /
If-Modified-Since), a bounded retry loop with exponential backoff, and a
clear ``NotModified`` signal so the caller can cheaply skip unchanged
categories.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .state import CategoryState


class FetchError(RuntimeError):
    """A category tarball could not be retrieved."""


class NotModified(Exception):
    """The server reported the resource is unchanged (HTTP 304)."""


@dataclass(slots=True)
class FetchResult:
    """A successfully downloaded tarball plus its caching headers."""

    content: bytes
    etag: str
    last_modified: str


class Fetcher:
    """Downloads category tarballs over HTTP with caching and retries."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: int,
        retries: int,
        user_agent: str,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retries = retries
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = user_agent

    def url_for(self, category: str) -> str:
        """Return the download URL for *category*."""
        return f"{self._base_url}/{category}.tar.gz"

    def fetch(self, category: str, state: CategoryState) -> FetchResult:
        """Download one category tarball.

        Uses conditional-request headers derived from *state*.

        Raises:
            NotModified: if the server returns HTTP 304.
            FetchError: if all attempts fail.
        """
        url = self.url_for(category)
        headers = _conditional_headers(state)
        last_exc: Exception | None = None

        for attempt in range(1, self._retries + 1):
            try:
                resp = self._session.get(
                    url, headers=headers, timeout=self._timeout
                )
                if resp.status_code == 304:
                    raise NotModified
                resp.raise_for_status()
                return FetchResult(
                    content=resp.content,
                    etag=resp.headers.get("ETag", ""),
                    last_modified=resp.headers.get("Last-Modified", ""),
                )
            except NotModified:
                raise
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self._retries:
                    time.sleep(_backoff_seconds(attempt))

        raise FetchError(
            f"{category}: download failed after {self._retries} attempt(s): {last_exc}"
        ) from last_exc


def _conditional_headers(state: CategoryState) -> dict[str, str]:
    headers: dict[str, str] = {}
    if state.etag:
        headers["If-None-Match"] = state.etag
    elif state.last_modified:
        headers["If-Modified-Since"] = state.last_modified
    return headers


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 1s, 2s, 4s, ... capped at 30s."""
    return min(2.0 ** (attempt - 1), 30.0)
