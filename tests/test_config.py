"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from egguard.categories import Disposition
from egguard.config import Config, ConfigError


def test_defaults_when_missing(tmp_path: Path) -> None:
    cfg = Config.load(tmp_path / "does-not-exist.yaml")
    assert cfg.policy_prefix == "60"
    assert cfg.lists_dir == Path("/etc/enforcegate-shared/lists")
    assert cfg.actions == {}


def test_load_overrides(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "policy_prefix: '40'\n"
        "default_action: warn\n"
        "actions:\n"
        "  adult: deny\n"
        "  child: permit\n"
        "skip:\n"
        "  - examen_pix\n",
        encoding="utf-8",
    )
    cfg = Config.load(path)
    assert cfg.policy_prefix == "40"
    assert cfg.default_action is Disposition.WARN
    assert cfg.actions["adult"] is Disposition.DENY
    assert cfg.actions["child"] is Disposition.PERMIT
    assert cfg.skip == ["examen_pix"]


def test_invalid_action_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("default_action: nonsense\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid action"):
        Config.load(path)


def test_invalid_prefix_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("policy_prefix: '999'\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="two-digit"):
        Config.load(path)


def test_non_mapping_top_level_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        Config.load(path)
