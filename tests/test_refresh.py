"""Tests for state persistence and category selection/resolution."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from egguard.categories import Action, get
from egguard.config import Config
from egguard.fetcher import Fetcher, FetchResult
from egguard.refresh import (
    CategoryResult,
    Outcome,
    Refresher,
    RefreshSummary,
    resolve_action,
    select_categories,
)
from egguard.state import CategoryState, StateStore


def test_summary_counts_loaded_domains() -> None:
    summary = RefreshSummary(
        results=[
            CategoryResult("a", Outcome.UPDATED, 100),
            CategoryResult("b", Outcome.UNCHANGED, 50),
            CategoryResult("c", Outcome.FAILED, 0, "boom"),
        ]
    )
    # failed categories load nothing; the other two contribute their counts.
    assert len(summary.loaded) == 2
    assert summary.total_domains == 150
    event = summary.as_event(dry_run=False)
    assert '"rules":2' in event
    assert '"domains":150' in event


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


class _OneShotFetcher:
    """Returns a fixed tarball for any category."""

    def __init__(self, content: bytes) -> None:
        self._content = content

    def fetch(self, category: str, state: CategoryState) -> FetchResult:
        return FetchResult(content=self._content, etag="", last_modified="")


class _WriteFailBridge:
    """Bridge whose list write fails like a read-only shared volume."""

    available = True

    def write_list(self, path: Path, domains: list[str]) -> None:
        raise PermissionError(13, "Permission denied", str(path))

    def write_policy(self, path: Path, text: str) -> None:  # pragma: no cover
        raise AssertionError("policy write should not be reached")

    def remove_list(self, path: Path) -> None:  # pragma: no cover
        pass

    def remove_policy(self, path: Path) -> None:  # pragma: no cover
        pass

    def reload(self) -> None:  # pragma: no cover
        raise AssertionError("reload should not run when nothing changed")

    def log(self, message: str) -> None:
        pass


class _CapturingBridge:
    """Bridge that records the policy text written for each category."""

    available = True

    def __init__(self) -> None:
        self.policies: dict[str, str] = {}

    def write_list(self, path: Path, domains: list[str]) -> None:
        pass

    def write_policy(self, path: Path, text: str) -> None:
        self.policies[path.name] = text

    def remove_list(self, path: Path) -> None:
        pass

    def remove_policy(self, path: Path) -> None:
        pass

    def reload(self) -> None:
        pass

    def log(self, message: str) -> None:
        pass


def test_action_override_wins(sample_tarball: bytes, tmp_path: Path) -> None:
    # `press` suggests warn; a per-category forced action must take precedence.
    bridge = _CapturingBridge()
    refresher = Refresher(
        Config(),
        cast(Fetcher, _OneShotFetcher(sample_tarball)),
        StateStore(tmp_path),
        bridge,
        actions={"press": Action.DENY},
    )

    refresher.run([get("press")])

    text = next(iter(bridge.policies.values()))
    assert "action: deny" in text


def test_write_oserror_fails_only_that_category(
    sample_tarball: bytes, tmp_path: Path
) -> None:
    # A bridge OSError must surface as a clean per-category failure, not an
    # uncaught traceback that aborts the run.
    refresher = Refresher(
        Config(),
        cast(Fetcher, _OneShotFetcher(sample_tarball)),
        StateStore(tmp_path),
        _WriteFailBridge(),
    )

    summary = refresher.run([get("adult")])

    assert [r.outcome for r in summary.results] == [Outcome.FAILED]
    assert "Permission denied" in summary.results[0].message
    assert summary.failed and not summary.reloaded


def test_resolve_action_priority() -> None:
    adult = get("adult")
    # 1. explicit override wins
    cfg = Config(actions={"adult": Action.WARN}, default_action=Action.PERMIT)
    assert resolve_action(adult, cfg) is Action.WARN
    # 2. default_action when no override
    cfg = Config(default_action=Action.PERMIT)
    assert resolve_action(adult, cfg) is Action.PERMIT
    # 3. catalogue suggestion when neither set
    assert resolve_action(adult, Config()) is Action.DENY
