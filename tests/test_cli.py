"""Tests for argument parsing and dispatch."""

from __future__ import annotations

import pytest

from egguard.categories import Disposition
from egguard.cli import EXIT_OK, build_parser, main


def test_no_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    # A bare `egguard` shows help and exits cleanly, rather than doing anything
    # side-effecting or crashing on the missing refresh options.
    rc = main([])

    out = capsys.readouterr().out
    assert rc == EXIT_OK
    assert "usage:" in out
    assert "refresh" in out


def test_refresh_takes_positional_categories() -> None:
    args = build_parser().parse_args(["refresh", "-n", "adult", "malware"])

    assert args.command == "refresh"
    assert args.dry_run is True
    assert args.categories == ["adult", "malware"]


def test_refresh_without_categories_is_empty() -> None:
    args = build_parser().parse_args(["refresh"])

    assert args.categories == []
    assert args.dry_run is False
    assert args.action is None


def test_action_flag_accepts_names_and_aliases() -> None:
    parser = build_parser()

    assert parser.parse_args(
        ["refresh", "adult", "--action", "warn"]
    ).action is (Disposition.WARN)
    # friendly aliases
    assert parser.parse_args(
        ["refresh", "adult", "--action", "block"]
    ).action is (Disposition.DENY)
    assert parser.parse_args(
        ["refresh", "adult", "--action", "allow"]
    ).action is (Disposition.PERMIT)


def test_action_flag_rejects_invalid() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["refresh", "adult", "--action", "nope"])
