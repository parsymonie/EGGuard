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


def test_url_for_abusech_embeds_key_and_remote_path() -> None:
    fetcher = _fetcher(
        abusech_base_url="https://abuse.example/exports",
        abusech_auth_key="SECRET",
    )
    # name is "urlhaus" but the remote path is "hostfile".
    assert (
        fetcher.url_for(get("urlhaus"))
        == "https://abuse.example/exports/SECRET/hostfile"
    )


def test_abusech_without_key_fails_clearly() -> None:
    with pytest.raises(FetchError, match="abusech_auth_key"):
        _fetcher().fetch(get("urlhaus"))


class _FailingSession:
    """A session whose GET fails with the URL in the message (like requests)."""

    headers: ClassVar[dict[str, str]] = {}

    def get(
        self, url: str, headers: object = None, timeout: object = None
    ) -> object:
        raise requests.ConnectionError(f"failed connecting to {url}")


def test_fetch_error_redacts_the_auth_key() -> None:
    fetcher = Fetcher(
        "http://ut1.example",
        timeout=10,
        retries=1,
        user_agent="test",
        abusech_base_url="https://abuse.example/exports",
        abusech_auth_key="SUPERSECRET",
        session=cast(requests.Session, _FailingSession()),
    )
    with pytest.raises(FetchError) as excinfo:
        fetcher.fetch(get("urlhaus"))

    message = str(excinfo.value)
    assert "SUPERSECRET" not in message  # the key must never leak
    assert "<auth-key>" in message
