"""Tests for policy file rendering."""

from __future__ import annotations

from pathlib import Path

from egguard.categories import Category, Disposition
from egguard.policy import render_policy


def test_render_contains_expected_fields() -> None:
    cat = Category("adult", "Adult content", Disposition.DENY)
    text = render_policy(
        cat,
        list_path=Path("/etc/enforcegate-shared/lists/ut1-adult.list"),
        action=Disposition.DENY,
    )
    assert "ut1-adult: {" in text
    assert (
        "match-domain-list: /etc/enforcegate-shared/lists/ut1-adult.list"
        in text
    )
    assert "action: deny" in text
    assert "application: https" in text
    assert "description: Adult content" in text
    assert "CC BY-SA 4.0" in text


def test_action_override_is_respected() -> None:
    cat = Category("press", "News and press", Disposition.WARN)
    text = render_policy(
        cat, list_path=Path("/x/ut1-press.list"), action=Disposition.PERMIT
    )
    assert "action: permit" in text


def test_description_braces_are_sanitised() -> None:
    cat = Category("weird", "has {braces} and\nnewline", Disposition.DENY)
    text = render_policy(
        cat, list_path=Path("/x.list"), action=Disposition.DENY
    )
    # The single-line value must not contain raw braces or newlines that
    # would break the policy block.
    desc_line = next(
        line
        for line in text.splitlines()
        if line.strip().startswith("description:")
    )
    assert "{" not in desc_line
    assert "}" not in desc_line
