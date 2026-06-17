"""Tests for the curses picker's pure helpers.

The curses loop itself needs a terminal and isn't unit-tested; the row
rendering and labels are pulled out so they can be.
"""

from __future__ import annotations

from egguard.categories import Action, get
from egguard.tui import _cycle_action, action_label, format_row, progress_bar


def test_action_label() -> None:
    assert action_label(None) == "default"
    assert action_label(Action.DENY) == "deny"


def test_cycle_action_wraps_through_none() -> None:
    assert _cycle_action(None) is Action.DENY
    assert _cycle_action(Action.PERMIT) is None  # last wraps back to default


def test_progress_bar() -> None:
    assert progress_bar(0, 4, 8) == "[--------]   0%"
    assert progress_bar(2, 4, 8) == "[####----]  50%"
    assert progress_bar(4, 4, 8) == "[########] 100%"
    # a zero total is treated as complete, not a divide-by-zero
    assert "100%" in progress_bar(0, 0, 8)


def test_format_row_marks_state_and_catalogue_action() -> None:
    category = get("social_networks")  # catalogue suggests warn
    row = format_row(
        category,
        selected=True,
        installed=True,
        action=None,
        cursor=True,
        name_width=20,
    )

    assert row.startswith(">")  # cursor
    assert "[x]" in row  # selected
    assert " * " in row  # installed marker
    assert "warn" in row  # catalogue action shown when no override
    assert "social_networks" in row


def test_format_row_shows_action_override() -> None:
    category = get("social_networks")
    row = format_row(
        category,
        selected=False,
        installed=False,
        action=Action.DENY,
        cursor=False,
        name_width=20,
    )

    assert "[ ]" in row
    assert "deny" in row  # override shown instead of the catalogue warn
