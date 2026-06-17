"""Tests for the curses picker's pure helpers.

The curses loop itself needs a terminal and isn't unit-tested; the row
rendering and labels are pulled out so they can be.
"""

from __future__ import annotations

from egguard.categories import Action, get
from egguard.tui import action_label, format_row


def test_action_label() -> None:
    assert action_label(None) == "default"
    assert action_label(Action.DENY) == "deny"


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
