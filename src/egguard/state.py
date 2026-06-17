"""Per-category download state.

EGGuard records the ETag, Last-Modified header, content hash, and domain
count of the last successful download for every category. This lets it
issue conditional HTTP requests and skip writing files when nothing has
changed, which keeps load off the UT1 servers and avoids needless engine
reloads.

State is stored as one small JSON file per category under the toolbox's
own writable volume, so it survives container recreation.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class CategoryState:
    """Cached metadata about the last successful fetch of one category.

    A category is considered *installed* once it has a saved state. ``action``
    records the disposition it was installed with (empty when the action is
    left to config/catalogue), so a later ``update`` keeps that choice.
    """

    etag: str = ""
    last_modified: str = ""
    sha256: str = ""
    domain_count: int = 0
    last_success: float = 0.0
    action: str = ""


class StateStore:
    """Reads and writes :class:`CategoryState` files under a directory."""

    def __init__(self, state_dir: Path) -> None:
        self._dir = state_dir

    def _path(self, category: str) -> Path:
        return self._dir / f"{category}.json"

    def exists(self, category: str) -> bool:
        """True if *category* is installed (has a saved state file)."""
        return self._path(category).exists()

    def installed(self) -> list[str]:
        """Return the names of all installed categories, sorted."""
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def remove(self, category: str) -> None:
        """Delete the stored state for *category*, if any."""
        self._path(category).unlink(missing_ok=True)

    def load(self, category: str) -> CategoryState:
        """Return the stored state for *category*, or a blank state."""
        path = self._path(category)
        if not path.exists():
            return CategoryState()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable state is non-fatal: treat as "no state".
            return CategoryState()
        return CategoryState(
            etag=str(data.get("etag", "")),
            last_modified=str(data.get("last_modified", "")),
            sha256=str(data.get("sha256", "")),
            domain_count=int(data.get("domain_count", 0)),
            last_success=float(data.get("last_success", 0.0)),
            action=str(data.get("action", "")),
        )

    def save(self, category: str, state: CategoryState) -> None:
        """Persist *state* for *category*, stamping the success time."""
        state.last_success = time.time()
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path(category).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        # Atomic replace so a crash mid-write never leaves a partial file.
        tmp.replace(self._path(category))
