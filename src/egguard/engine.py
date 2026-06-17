"""Bridge to the EnforceGate toolbox helper library.

Inside the toolbox sidecar, EGGuard uses the bundled
``enforcegate_toolbox`` package to write lists and policies into the
shared volume and to trigger an engine reload. Outside the toolbox (local
development, CI, ``--dry-run``), that package is absent, so this module
provides a filesystem-backed fallback with the same interface.

The active backend is chosen once at import time and exposed through the
:class:`EngineBridge` protocol so the rest of the code never branches on
"are we in the toolbox?".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

_log = logging.getLogger("egguard.engine")


@runtime_checkable
class EngineBridge(Protocol):
    """The operations EGGuard needs from its environment."""

    available: bool
    """True when the real toolbox helper library is in use."""

    def write_list(self, path: Path, domains: list[str]) -> None:
        """Write a domain list (one host per line) to *path*."""

    def write_policy(self, path: Path, text: str) -> None:
        """Write a ``.policy`` file to *path*."""

    def remove_list(self, path: Path) -> None:
        """Delete a domain list at *path*, if it exists."""

    def remove_policy(self, path: Path) -> None:
        """Delete a ``.policy`` file at *path*, if it exists."""

    def reload(self) -> None:
        """Ask the engine to recompile and reload its policy set."""

    def log(self, message: str) -> None:
        """Emit an operational log line (JSON, SIEM-ingestible)."""


class _ToolboxBridge:
    """Backend that delegates to the real ``enforcegate_toolbox`` library."""

    available = True

    def __init__(self) -> None:
        from enforcegate_toolbox import engine, lists, log, policies

        self._engine = engine
        self._lists = lists
        self._policies = policies
        self._log = log

    def write_list(self, path: Path, domains: list[str]) -> None:
        # The toolbox library owns the shared lists dir and appends the
        # ``.list`` extension itself, so it wants the bare stem with no
        # separators and no suffix.
        self._lists.write(path.stem, domains)

    def write_policy(self, path: Path, text: str) -> None:
        # Same contract as lists.write: bare stem, the library adds ``.policy``.
        self._policies.write(path.stem, text)

    def remove_list(self, path: Path) -> None:
        # The library has no documented delete; EGGuard wrote the file at this
        # path (in the shared dir it owns), so unlink it directly.
        path.unlink(missing_ok=True)

    def remove_policy(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def reload(self) -> None:
        self._engine.reload()

    def log(self, message: str) -> None:
        self._log.info(message)


class _LocalBridge:
    """Filesystem fallback used outside the toolbox.

    Writes files directly and logs the reload instead of performing it.
    """

    available = False

    def write_list(self, path: Path, domains: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(domains) + "\n", encoding="utf-8")

    def write_policy(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def remove_list(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def remove_policy(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def reload(self) -> None:
        _log.info("(local) engine reload skipped — toolbox library unavailable")

    def log(self, message: str) -> None:
        _log.info(message)


def get_bridge() -> EngineBridge:
    """Return the toolbox bridge if available, else the local fallback."""
    try:
        return _ToolboxBridge()
    except ImportError:
        return _LocalBridge()


def json_event(**fields: object) -> str:
    """Serialise *fields* as a compact single-line JSON event."""
    return json.dumps(fields, separators=(",", ":"), sort_keys=True)
