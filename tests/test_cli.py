"""Tests for argument parsing and dispatch."""

from __future__ import annotations

import pytest

from egguard.categories import Action
from egguard.cli import (
    EXIT_OK,
    _relative_age,
    _status_line,
    _summary_line,
    build_parser,
    main,
)
from egguard.refresh import CategoryResult, Outcome, RefreshSummary


def test_relative_age() -> None:
    now = 1_000_000_000.0
    assert _relative_age(0, now) == ""  # never updated
    assert _relative_age(now - 30, now) == "30s ago"
    assert _relative_age(now - 90, now) == "1m ago"
    assert _relative_age(now - 3 * 3600, now) == "3h ago"
    assert _relative_age(now - 2 * 86400, now) == "2d ago"
    assert _relative_age(now - 21 * 86400, now) == "3w ago"
    assert _relative_age(now + 100, now) == "0s ago"  # future clamps to 0


def test_status_line_formats_each_outcome() -> None:
    updated = CategoryResult("adult", Outcome.UPDATED, 42)
    assert _status_line(updated) == "+ adult  updated (42 domains)"

    unchanged = CategoryResult("ai", Outcome.UNCHANGED, 5)
    assert _status_line(unchanged) == "= ai  unchanged"

    failed = CategoryResult("x", Outcome.FAILED, message="boom")
    assert _status_line(failed) == "! x  failed: boom"


def test_summary_line() -> None:
    summary = RefreshSummary(
        results=[
            CategoryResult("a", Outcome.UPDATED, 1),
            CategoryResult("b", Outcome.UNCHANGED, 0),
        ],
        reloaded=True,
    )
    line = _summary_line(summary, dry_run=False)
    assert "1 updated" in line
    assert "1 unchanged" in line
    assert "0 failed" in line
    assert "1 domains" in line
    assert "engine reloaded" in line


def test_no_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    # A bare `egguard` shows help and exits cleanly, rather than doing anything
    # side-effecting or crashing on the missing subcommand.
    rc = main([])

    out = capsys.readouterr().out
    assert rc == EXIT_OK
    assert "usage:" in out
    assert "install" in out


def test_install_takes_positional_categories() -> None:
    args = build_parser().parse_args(["install", "-n", "adult", "malware"])

    assert args.command == "install"
    assert args.dry_run is True
    assert args.categories == ["adult", "malware"]


def test_update_without_categories_is_empty() -> None:
    args = build_parser().parse_args(["update"])

    assert args.command == "update"
    assert args.categories == []
    assert args.dry_run is False
    assert args.action is None


def test_install_requires_a_category() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["install"])


def test_action_flag_accepts_names_and_aliases() -> None:
    parser = build_parser()

    assert parser.parse_args(
        ["install", "adult", "--action", "warn"]
    ).action is (Action.WARN)
    # friendly aliases
    assert parser.parse_args(
        ["install", "adult", "--action", "block"]
    ).action is (Action.DENY)
    assert parser.parse_args(
        ["install", "adult", "--action", "allow"]
    ).action is (Action.PERMIT)


def test_action_flag_rejects_invalid() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["install", "adult", "--action", "nope"])
