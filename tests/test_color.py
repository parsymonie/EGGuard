"""Tests for the pink CLI colouring."""

from __future__ import annotations

import io

import pytest

from egguard.color import pink


class _Tty(io.StringIO):
    """A stream that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


def test_plain_for_non_tty() -> None:
    # A pipe/file (not a TTY) must stay clean for parsing.
    assert pink("hi", io.StringIO()) == "hi"


def test_pink_wraps_for_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = pink("hi", _Tty())

    assert out != "hi"
    assert out.startswith("\033[")
    assert out.endswith("\033[0m")
    assert "hi" in out


def test_no_color_env_disables_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert pink("hi", _Tty()) == "hi"
