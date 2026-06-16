"""Tests for state persistence and category selection/resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from egguard.categories import Disposition, get
from egguard.config import Config
from egguard.refresh import resolve_action, select_categories
from egguard.state import CategoryState, StateStore


def test_state_roundtrip(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    assert store.load("adult") == CategoryState()  # blank when absent

    store.save(
        "adult", CategoryState(etag='"abc"', sha256="deadbeef", domain_count=42)
    )
    loaded = store.load("adult")
    assert loaded.etag == '"abc"'
    assert loaded.sha256 == "deadbeef"
    assert loaded.domain_count == 42
    assert loaded.last_success > 0  # stamped on save


def test_corrupt_state_is_blank(tmp_path: Path) -> None:
    (tmp_path / "adult.json").write_text("{not json", encoding="utf-8")
    assert StateStore(tmp_path).load("adult") == CategoryState()


def test_select_explicit_overrides_config() -> None:
    cfg = Config(skip=["adult"])
    selected = select_categories(cfg, ["adult", "malware"])
    assert [c.name for c in selected] == ["adult", "malware"]


def test_select_unknown_raises() -> None:
    with pytest.raises(KeyError):
        select_categories(Config(), ["not-a-real-category"])


def test_select_include_wins_over_skip() -> None:
    cfg = Config(include=["adult", "phishing"], skip=["adult"])
    names = {c.name for c in select_categories(cfg, None)}
    assert names == {"adult", "phishing"}


def test_select_skip_excludes() -> None:
    cfg = Config(skip=["adult"])
    names = {c.name for c in select_categories(cfg, None)}
    assert "adult" not in names
    assert "malware" in names


def test_resolve_action_priority() -> None:
    adult = get("adult")
    # 1. explicit override wins
    cfg = Config(
        actions={"adult": Disposition.WARN}, default_action=Disposition.PERMIT
    )
    assert resolve_action(adult, cfg) is Disposition.WARN
    # 2. default_action when no override
    cfg = Config(default_action=Disposition.PERMIT)
    assert resolve_action(adult, cfg) is Disposition.PERMIT
    # 3. catalogue suggestion when neither set
    assert resolve_action(adult, Config()) is Disposition.DENY
