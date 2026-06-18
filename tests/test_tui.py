"""Tests for the curses picker's pure helpers.

The curses loop itself needs a terminal and isn't unit-tested; the row
rendering and labels are pulled out so they can be.
"""

from __future__ import annotations

from egguard.categories import Action, get
from egguard.tui import _cycle_action, action_label, bar_fill, format_row


def test_action_label() -> None:
    assert action_label(None) == "default"
    assert action_label(Action.DENY) == "deny"


def test_cycle_action_advances_through_real_actions() -> None:
    # No 'default'/None state: cycling always moves to a concrete action, so the
    # first press visibly advances even when the row is already on deny.
    assert _cycle_action(Action.DENY) is Action.WARN
    assert _cycle_action(Action.WARN) is Action.AUP
    assert _cycle_action(Action.AUP) is Action.PERMIT
    assert _cycle_action(Action.PERMIT) is Action.DENY  # wraps


def test_bar_fill() -> None:
    assert bar_fill(0, 4, 8) == 0
    assert bar_fill(2, 4, 8) == 4
    assert bar_fill(4, 4, 8) == 8
    assert bar_fill(0, 0, 8) == 8  # zero total = complete, no divide-by-zero
    assert bar_fill(1, 4, 0) == 0  # zero width is safe


def test_format_row_marks_state_and_default_action() -> None:
    category = get("social_networks")
    row = format_row(
        category,
        selected=True,
        installed=True,
        action=None,
        default_action=Action.WARN,  # the action currently in effect
        cursor=True,
        name_width=20,
    )

    assert row.startswith(">")  # cursor
    assert "[x]" in row  # selected
    assert " * " in row  # installed marker
    assert "warn" in row  # the effective action shown when no override
    assert "social_networks" in row


def test_format_row_shows_action_override() -> None:
    category = get("social_networks")
    row = format_row(
        category,
        selected=False,
        installed=False,
        action=Action.DENY,
        default_action=Action.WARN,
        cursor=False,
        name_width=20,
    )

    assert "[ ]" in row
    assert "deny" in row  # the per-row override wins over the default


def test_format_row_shows_source_when_requested() -> None:
    # With a source column, an abuse.ch feed is marked as such in the picker.
    row = format_row(
        get("urlhaus"),
        selected=False,
        installed=False,
        action=None,
        default_action=Action.DENY,
        cursor=False,
        name_width=20,
        source_width=8,
    )
    assert "abuse.ch" in row  # friendly source label
    assert "urlhaus" in row

    # Without a source column (single source), nothing extra is added.
    plain = format_row(
        get("adult"),
        selected=False,
        installed=False,
        action=None,
        default_action=Action.DENY,
        cursor=False,
        name_width=20,
    )
    assert "UT1" not in plain
