"""Tests for the source-aware fetcher: URL building and auth-key handling."""

from __future__ import annotations

from typing import ClassVar, cast

import pytest
import requests

from egguard.categories import get
from egguard.fetcher import Fetcher, FetchError


def _fetcher(
    *, abusech_base_url: str = "", abusech_auth_key: str = ""
) -> Fetcher:
    return Fetcher(
        "http://ut1.example/download",
        timeout=10,
        retries=1,
        user_agent="test",
        abusech_base_url=abusech_base_url,
        abusech_auth_key=abusech_auth_key,
    )


def test_url_for_ut1_tarball() -> None:
    assert (
        _fetcher().url_for(get("adult"))
        == "http://ut1.example/download/adult.tar.gz"
    )


def test_url_for_abusech_uses_remote_path_without_key() -> None:
    fetcher = _fetcher(
        abusech_base_url="https://abuse.example/downloads",
        abusech_auth_key="SECRET",
    )
    # name is "urlhaus" but the remote path is "hostfile"; the key is sent as
    # a header, so it must never appear in the URL.
    url = fetcher.url_for(get("urlhaus"))
    assert url == "https://abuse.example/downloads/hostfile/"
    assert "SECRET" not in url


def test_url_for_abusech_absolute_remote_used_as_is() -> None:
    fetcher = _fetcher(
        abusech_base_url="https://urlhaus.abuse.ch/downloads",
        abusech_auth_key="SECRET",
    )
    # threatfox carries an absolute URL (different host); it must be used
    # verbatim (with a trailing slash), not joined onto the URLhaus base.
    url = fetcher.url_for(get("threatfox"))
    assert url == "https://threatfox.abuse.ch/downloads/hostfile/"
    assert "urlhaus" not in url


def test_abusech_without_key_fails_clearly() -> None:
    with pytest.raises(FetchError, match="abusech_auth_key"):
        _fetcher().fetch(get("urlhaus"))


class _CapturingSession:
    """A session that records the request and fails, leaking what it saw.

    Mimics a library whose error text echoes the headers, so the redaction
    guard has something to scrub even now that the key travels in a header.
    """

    headers: ClassVar[dict[str, str]] = {}
    seen_headers: dict[str, str]

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: object = None,
    ) -> object:
        self.seen_headers = dict(headers or {})
        leaked = self.seen_headers.get("Auth-Key", "")
        raise requests.ConnectionError(f"failed: {url} (Auth-Key: {leaked})")


def test_fetch_sends_auth_key_header_and_redacts_it() -> None:
    session = _CapturingSession()
    fetcher = Fetcher(
        "http://ut1.example",
        timeout=10,
        retries=1,
        user_agent="test",
        abusech_base_url="https://abuse.example/downloads",
        abusech_auth_key="SUPERSECRET",
        session=cast(requests.Session, session),
    )
    with pytest.raises(FetchError) as excinfo:
        fetcher.fetch(get("urlhaus"))

    # the key is sent as a header, never in the URL
    assert session.seen_headers["Auth-Key"] == "SUPERSECRET"
    message = str(excinfo.value)
    assert "SUPERSECRET" not in message  # the key must never leak
    assert "<auth-key>" in message
