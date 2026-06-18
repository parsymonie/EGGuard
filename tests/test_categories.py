"""Tests for catalogue lookups and per-source feed naming."""

from __future__ import annotations

from egguard.categories import FMT_HOSTFILE, FMT_UT1_TARBALL, get


def test_ut1_feed_naming_unchanged() -> None:
    adult = get("adult")
    assert adult.source == "ut1"
    assert adult.fmt == FMT_UT1_TARBALL
    assert adult.fetch_path == "adult"
    assert adult.slug == "ut1-adult"
    assert adult.list_filename == "ut1-adult.list"
    assert adult.policy_filename("60") == "60-ut1-adult.policy"


def test_abusech_feed_naming() -> None:
    feed = get("urlhaus")
    assert feed.source == "abusech"
    assert feed.fmt == FMT_HOSTFILE
    assert feed.fetch_path == "hostfile"  # remote path differs from the name
    assert feed.slug == "abusech-urlhaus"
    assert feed.list_filename == "abusech-urlhaus.list"
    assert feed.policy_filename("60") == "60-abusech-urlhaus.policy"
