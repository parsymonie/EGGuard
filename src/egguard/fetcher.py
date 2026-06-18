"""HTTP fetching of category feeds.

Wraps :mod:`requests` with conditional-request support (ETag /
If-Modified-Since), a bounded retry loop with exponential backoff, and a clear
``NotModified`` signal so the caller can cheaply skip unchanged feeds. Both UT1
tarballs and abuse.ch exports (which embed a secret Auth-Key in the URL) are
handled; the key is never written into errors or logs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .categories import Category
from .state import CategoryState


class FetchError(RuntimeError):
    """A feed could not be retrieved."""


class NotModified(Exception):
    """The server reported the resource is unchanged (HTTP 304)."""


@dataclass(slots=True)
class FetchResult:
    """A successfully downloaded feed plus its caching headers."""

    content: bytes
    etag: str
    last_modified: str


class Fetcher:
    """Downloads category feeds over HTTP with caching and retries."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: int,
        retries: int,
        user_agent: str,
        abusech_base_url: str = "",
        abusech_auth_key: str = "",
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._abusech_base = abusech_base_url.rstrip("/")
        self._abusech_key = abusech_auth_key
        self._timeout = timeout
        self._retries = retries
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = user_agent

    def url_for(self, category: Category) -> str:
        """Return the download URL for *category* (may embed the auth key)."""
        if category.source == "abusech":
            return f"{self._abusech_base}/{self._abusech_key}/{category.fetch_path}"
        return f"{self._base_url}/{category.fetch_path}.tar.gz"

    def fetch(
        self, category: Category, state: CategoryState | None = None
    ) -> FetchResult:
        """Download one feed.

        Uses conditional-request headers derived from *state*. Pass ``None``
        (the default) for an unconditional fetch.

        Raises:
            NotModified: if the server returns HTTP 304.
            FetchError: if the feed can't be fetched (including a missing
                abuse.ch auth key) after all retries.
        """
        if category.source == "abusech" and not self._abusech_key:
            raise FetchError(
                f"{category.name}: abuse.ch feeds need 'abusech_auth_key' in "
                f"config (get a free key at https://auth.abuse.ch/)"
            )

        url = self.url_for(category)
        headers = _conditional_headers(state or CategoryState())
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

        # requests' exception text can contain the request URL (and thus the
        # abuse.ch auth key), so redact it before surfacing the error.
        message = (
            f"{category.name}: download failed after {self._retries} "
            f"attempt(s): {last_exc}"
        )
        raise FetchError(self._redact(message)) from None

    def _redact(self, text: str) -> str:
        if self._abusech_key:
            return text.replace(self._abusech_key, "<auth-key>")
        return text


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
