"""Tests for the engine bridges."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from egguard.engine import _LocalBridge, _ToolboxBridge


def _install_fake_toolbox(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Register a fake ``enforcegate_toolbox`` package and record its calls."""
    calls: dict[str, object] = {}

    lists = types.ModuleType("enforcegate_toolbox.lists")
    lists.write = lambda name, domains: calls.update(  # type: ignore[attr-defined]
        list_name=name, list_domains=domains
    )
    policies = types.ModuleType("enforcegate_toolbox.policies")
    policies.write = lambda name, text: calls.update(  # type: ignore[attr-defined]
        policy_name=name, policy_text=text
    )
    engine = types.ModuleType("enforcegate_toolbox.engine")
    engine.reload = lambda: calls.update(reloaded=True)  # type: ignore[attr-defined]
    log = types.ModuleType("enforcegate_toolbox.log")
    log.info = lambda message: calls.update(logged=message)  # type: ignore[attr-defined]

    pkg = types.ModuleType("enforcegate_toolbox")
    monkeypatch.setitem(sys.modules, "enforcegate_toolbox", pkg)
    monkeypatch.setitem(sys.modules, "enforcegate_toolbox.lists", lists)
    monkeypatch.setitem(sys.modules, "enforcegate_toolbox.policies", policies)
    monkeypatch.setitem(sys.modules, "enforcegate_toolbox.engine", engine)
    monkeypatch.setitem(sys.modules, "enforcegate_toolbox.log", log)
    return calls


def test_toolbox_bridge_passes_bare_filenames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The toolbox library rejects paths with separators and appends the
    # extension itself, so the bridge must hand it the bare stem, never the
    # full shared-volume path.
    calls = _install_fake_toolbox(monkeypatch)
    bridge = _ToolboxBridge()

    bridge.write_list(
        Path("/etc/enforcegate-shared/lists/ut1-social_networks.list"),
        ["a.example", "b.example"],
    )
    bridge.write_policy(
        Path("/etc/enforcegate-shared/policies/60-ut1-social_networks.policy"),
        "ut1-social_networks: {}\n",
    )

    # The library appends .list / .policy itself, so pass the bare stem.
    assert calls["list_name"] == "ut1-social_networks"
    assert calls["policy_name"] == "60-ut1-social_networks"


def test_local_bridge_writes_full_path(tmp_path: Path) -> None:
    bridge = _LocalBridge()
    list_path = tmp_path / "lists" / "ut1-x.list"

    bridge.write_list(list_path, ["a.example", "b.example"])

    assert list_path.read_text(encoding="utf-8") == "a.example\nb.example\n"
