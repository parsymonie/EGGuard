"""Tests for argument parsing and dispatch."""

from __future__ import annotations

import pytest

from egguard.categories import Action
from egguard.cli import EXIT_OK, build_parser, main


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
