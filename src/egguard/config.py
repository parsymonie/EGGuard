"""Configuration loading for EGGuard.

Configuration is a single YAML file. Every key is optional; sensible
defaults are baked in so EGGuard runs with no config at all. The defaults
target the EnforceGate vX toolbox sidecar's shared-volume layout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .categories import Action

# --------------------------------------------------------------------------- #
# Defaults — aligned with the EnforceGate vX toolbox documentation.
# --------------------------------------------------------------------------- #
DEFAULT_BASE_URL = "http://dsi.ut-capitole.fr/blacklists/download"
DEFAULT_LISTS_DIR = Path("/etc/enforcegate-shared/lists")
# EnforceGate vX 2026.32.0 renamed the shared policies dir to rules.d.
# On older (< 2026.32.0) appliances, override with
# policies_dir: /etc/enforcegate-shared/policies.
DEFAULT_POLICIES_DIR = Path("/etc/enforcegate-shared/rules.d")
DEFAULT_STATE_DIR = Path("/var/lib/enforcegate-toolbox/state/egguard")
DEFAULT_POLICY_PREFIX = "60"
DEFAULT_TIMEOUT = 120
DEFAULT_RETRIES = 3
DEFAULT_MIN_DOMAINS = 1
DEFAULT_USER_AGENT = "EGGuard/2.4 (EnforceGate vX toolbox; +https://github.com/parsymonie/egguard)"

# abuse.ch URLhaus exports require a free Auth-Key (https://auth.abuse.ch/),
# sent as the `Auth-Key` HTTP header (so it never appears in a URL). Leave
# abusech_auth_key empty to disable the abuse.ch feeds.
DEFAULT_ABUSECH_BASE_URL = "https://urlhaus.abuse.ch/downloads"

# Env var used as a fallback when the config file carries no abuse.ch key, so
# the secret can stay out of config.yaml on disk.
ENV_ABUSECH_AUTH_KEY = "EGGUARD_ABUSECH_AUTH_KEY"

# Example placeholders from our docs/config; treat these as "no key set" so the
# user gets a clear "need an Auth-Key" message instead of a failed download.
_ABUSECH_KEY_PLACEHOLDERS = frozenset(
    {
        "your-abuse-ch-auth-key",
        "your-auth-key",
        "your-real-auth-key",
        "changeme",
    }
)


class ConfigError(ValueError):
    """Raised when a configuration file is structurally invalid."""


@dataclass(slots=True)
class Config:
    """Resolved EGGuard configuration."""

    base_url: str = DEFAULT_BASE_URL
    lists_dir: Path = DEFAULT_LISTS_DIR
    policies_dir: Path = DEFAULT_POLICIES_DIR
    state_dir: Path = DEFAULT_STATE_DIR
    policy_prefix: str = DEFAULT_POLICY_PREFIX
    timeout: int = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES
    min_domains: int = DEFAULT_MIN_DOMAINS
    user_agent: str = DEFAULT_USER_AGENT

    # Default action for categories without an explicit override.
    default_action: Action | None = None

    # Per-category action overrides (name -> Action).
    actions: dict[str, Action] = field(default_factory=dict)

    # Category selection. ``include`` wins over ``skip`` when non-empty.
    include: list[str] = field(default_factory=list)
    skip: list[str] = field(default_factory=list)

    # abuse.ch feeds. An empty auth key disables them.
    abusech_base_url: str = DEFAULT_ABUSECH_BASE_URL
    abusech_auth_key: str = ""

    def __post_init__(self) -> None:
        # An explicit key in the config file wins; otherwise fall back to the
        # environment so the secret need not live on disk.
        if not self.abusech_auth_key:
            self.abusech_auth_key = _clean_auth_key(
                os.environ.get(ENV_ABUSECH_AUTH_KEY, "")
            )
        if not _is_two_digit_prefix(self.policy_prefix):
            raise ConfigError(
                f"policy_prefix must be a two-digit string, got {self.policy_prefix!r}"
            )
        if self.timeout <= 0:
            raise ConfigError("timeout must be positive")
        if self.retries < 0:
            raise ConfigError("retries must be >= 0")
        if self.min_domains < 0:
            raise ConfigError("min_domains must be >= 0")

    @classmethod
    def load(cls, path: Path | None) -> Config:
        """Load configuration from *path*, or return defaults if it is missing.

        Raises:
            ConfigError: if the file exists but is malformed.
        """
        if path is None or not path.exists():
            return cls()

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path}: invalid YAML: {exc}") from exc

        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ConfigError(f"{path}: top level must be a mapping")

        return cls._from_mapping(raw, source=path)

    @classmethod
    def _from_mapping(cls, raw: dict[str, Any], *, source: Path) -> Config:
        def _path(key: str, default: Path) -> Path:
            value = raw.get(key)
            return Path(value) if value is not None else default

        cfg = cls(
            base_url=str(raw.get("base_url", DEFAULT_BASE_URL)),
            lists_dir=_path("lists_dir", DEFAULT_LISTS_DIR),
            policies_dir=_path("policies_dir", DEFAULT_POLICIES_DIR),
            state_dir=_path("state_dir", DEFAULT_STATE_DIR),
            policy_prefix=str(raw.get("policy_prefix", DEFAULT_POLICY_PREFIX)),
            timeout=int(raw.get("timeout", DEFAULT_TIMEOUT)),
            retries=int(raw.get("retries", DEFAULT_RETRIES)),
            min_domains=int(raw.get("min_domains", DEFAULT_MIN_DOMAINS)),
            user_agent=str(raw.get("user_agent", DEFAULT_USER_AGENT)),
            default_action=_parse_action(raw.get("default_action"), source),
            actions=_parse_actions(raw.get("actions"), source),
            include=_parse_str_list(raw.get("include"), "include", source),
            skip=_parse_str_list(raw.get("skip"), "skip", source),
            abusech_base_url=str(
                raw.get("abusech_base_url", DEFAULT_ABUSECH_BASE_URL)
            ),
            abusech_auth_key=_clean_auth_key(raw.get("abusech_auth_key", "")),
        )
        return cfg


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _is_two_digit_prefix(value: str) -> bool:
    return len(value) == 2 and value.isdigit()


def _parse_action(value: Any, source: Path) -> Action | None:
    if value is None:
        return None
    try:
        return Action(str(value))
    except ValueError as exc:
        valid = ", ".join(d.value for d in Action)
        raise ConfigError(
            f"{source}: invalid action {value!r}; expected one of: {valid}"
        ) from exc


def _parse_actions(value: Any, source: Path) -> dict[str, Action]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: 'actions' must be a mapping")
    return {
        str(name): _require_action(act, source) for name, act in value.items()
    }


def _require_action(value: Any, source: Path) -> Action:
    action = _parse_action(value, source)
    if action is None:
        raise ConfigError(f"{source}: action may not be null")
    return action


def _parse_str_list(value: Any, key: str, source: Path) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(v, str) for v in value
    ):
        raise ConfigError(f"{source}: '{key}' must be a list of strings")
    return list(value)


def _clean_auth_key(value: Any) -> str:
    """Return the auth key, or '' if it is blank or a known placeholder."""
    key = str(value).strip()
    if key.lower().replace("_", "-") in _ABUSECH_KEY_PLACEHOLDERS:
        return ""
    return key
