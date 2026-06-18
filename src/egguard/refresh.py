"""Refresh orchestration.

Coordinates the per-category pipeline (fetch -> parse -> write list ->
write policy -> record state) across the selected categories, triggers a
single engine reload at the end if anything changed, and returns a
structured summary.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from . import categories as catalogue
from .categories import Action, Category
from .config import Config
from .engine import EngineBridge, json_event
from .fetcher import Fetcher, FetchError, NotModified
from .parser import ParseError, extract_domains
from .policy import render_policy
from .state import CategoryState, StateStore

_log = logging.getLogger("egguard.refresh")


class Outcome(Enum):
    """The result of refreshing a single category."""

    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass(slots=True)
class CategoryResult:
    """Per-category outcome with detail for the summary."""

    name: str
    outcome: Outcome
    domain_count: int = 0
    message: str = ""


@dataclass(slots=True)
class RefreshSummary:
    """Aggregate result of a refresh run."""

    results: list[CategoryResult] = field(default_factory=list)
    reloaded: bool = False
    elapsed_seconds: float = 0.0

    @property
    def updated(self) -> list[CategoryResult]:
        return [r for r in self.results if r.outcome is Outcome.UPDATED]

    @property
    def failed(self) -> list[CategoryResult]:
        return [r for r in self.results if r.outcome is Outcome.FAILED]

    @property
    def changed(self) -> bool:
        return bool(self.updated)

    def as_event(self, *, dry_run: bool) -> str:
        """Render a one-line JSON summary for logs / SIEM ingestion."""
        return json_event(
            event="egguard-refresh",
            total=len(self.results),
            updated=len(self.updated),
            failed=len(self.failed),
            reloaded=self.reloaded,
            dry_run=dry_run,
            elapsed_s=round(self.elapsed_seconds, 1),
        )


def select_categories(
    cfg: Config, explicit: list[str] | None
) -> list[Category]:
    """Resolve which categories to process.

    Priority: explicit CLI selection > config ``include`` > config ``skip``.

    Raises:
        KeyError: if an explicitly named category is unknown.
    """
    if explicit:
        return [catalogue.get(name) for name in explicit]

    if cfg.include:
        wanted = set(cfg.include)
        unknown = wanted - set(catalogue.all_names())
        if unknown:
            _log.warning(
                "config 'include' names unknown categories: %s",
                ", ".join(sorted(unknown)),
            )
        return [c for c in catalogue.CATALOGUE if c.name in wanted]

    skip = set(cfg.skip)
    return [c for c in catalogue.CATALOGUE if c.name not in skip]


def resolve_action(
    category: Category,
    cfg: Config,
    *,
    override: Action | None = None,
    installed: Action | None = None,
) -> Action:
    """Resolve the action for *category*.

    Priority: CLI ``override`` > config per-category > the action it was
    ``installed`` with > config default > catalogue suggestion.
    """
    if override is not None:
        return override
    if category.name in cfg.actions:
        return cfg.actions[category.name]
    if installed is not None:
        return installed
    if cfg.default_action is not None:
        return cfg.default_action
    return category.disposition


def _disposition_or_none(value: str) -> Action | None:
    """Parse a stored action string into a Action, or None if blank/bad."""
    if not value:
        return None
    try:
        return Action(value)
    except ValueError:
        return None


def remove_category(
    category: Category,
    cfg: Config,
    store: StateStore,
    bridge: EngineBridge,
) -> bool:
    """Delete *category*'s generated list, policy, and state.

    Returns True if the category was installed (something existed to remove).
    The caller is responsible for reloading the engine afterwards.
    """
    list_path = cfg.lists_dir / category.list_filename
    policy_path = cfg.policies_dir / category.policy_filename(cfg.policy_prefix)
    existed = (
        store.exists(category.name)
        or list_path.exists()
        or policy_path.exists()
    )
    bridge.remove_list(list_path)
    bridge.remove_policy(policy_path)
    store.remove(category.name)
    return existed


class Refresher:
    """Runs the refresh pipeline for a set of categories."""

    def __init__(
        self,
        cfg: Config,
        fetcher: Fetcher,
        store: StateStore,
        bridge: EngineBridge,
        *,
        dry_run: bool = False,
        actions: dict[str, Action] | None = None,
    ) -> None:
        self._cfg = cfg
        self._fetcher = fetcher
        self._store = store
        self._bridge = bridge
        self._dry_run = dry_run
        # Per-category forced actions (e.g. from `--action` or the picker).
        self._actions = actions or {}

    def run(
        self,
        selected: list[Category],
        on_progress: Callable[[int, int, CategoryResult], None] | None = None,
        *,
        quiet: bool = False,
    ) -> RefreshSummary:
        """Refresh every category in *selected* and reload once if needed.

        *on_progress* (if given) is called as ``(done, total, result)`` after
        each category, so a UI can drive a progress bar. Set *quiet* to skip
        the one-line JSON summary log (e.g. when a UI owns the screen).
        """
        summary = RefreshSummary()
        started = time.monotonic()
        total = len(selected)

        for index, category in enumerate(selected, start=1):
            result = self._refresh_one(category)
            summary.results.append(result)
            _log_result(result)
            if on_progress is not None:
                on_progress(index, total, result)

        summary.elapsed_seconds = time.monotonic() - started

        if summary.changed and not self._dry_run:
            summary.reloaded = self._reload()

        if not quiet:
            self._bridge.log(summary.as_event(dry_run=self._dry_run))
        return summary

    def _refresh_one(self, category: Category) -> CategoryResult:
        state = self._store.load(category.name)
        try:
            fetched = self._fetcher.fetch(category.name, state)
        except NotModified:
            return CategoryResult(
                category.name,
                Outcome.UNCHANGED,
                state.domain_count,
                "304 Not Modified",
            )
        except FetchError as exc:
            return CategoryResult(
                category.name, Outcome.FAILED, message=str(exc)
            )

        sha256 = hashlib.sha256(fetched.content).hexdigest()
        if sha256 == state.sha256:
            return CategoryResult(
                category.name,
                Outcome.UNCHANGED,
                state.domain_count,
                "content unchanged",
            )

        try:
            domains = extract_domains(fetched.content)
        except ParseError as exc:
            return CategoryResult(
                category.name, Outcome.FAILED, message=str(exc)
            )

        if len(domains) < self._cfg.min_domains:
            return CategoryResult(
                category.name,
                Outcome.FAILED,
                message=(
                    f"only {len(domains)} domains (min {self._cfg.min_domains}) — rejected"
                ),
            )

        override = self._actions.get(category.name)
        action = resolve_action(
            category,
            self._cfg,
            override=override,
            installed=_disposition_or_none(state.action),
        )

        if not self._dry_run:
            # A write failure (e.g. the shared volume is read-only) must fail
            # only this category, not abort the whole run.
            try:
                self._write(category, domains, action)
            except OSError as exc:
                return CategoryResult(
                    category.name, Outcome.FAILED, message=str(exc)
                )
            # Persist the action only when explicitly chosen on this run;
            # otherwise keep whatever the category was installed with.
            saved_action = (
                override.value if override is not None else state.action
            )
            self._store.save(
                category.name,
                CategoryState(
                    etag=fetched.etag,
                    last_modified=fetched.last_modified,
                    sha256=sha256,
                    domain_count=len(domains),
                    action=saved_action,
                ),
            )

        return CategoryResult(category.name, Outcome.UPDATED, len(domains))

    def _write(
        self, category: Category, domains: list[str], action: Action
    ) -> None:
        list_path = self._cfg.lists_dir / category.list_filename
        policy_path = self._cfg.policies_dir / category.policy_filename(
            self._cfg.policy_prefix
        )
        self._bridge.write_list(list_path, domains)
        self._bridge.write_policy(
            policy_path,
            render_policy(category, list_path=list_path, action=action),
        )

    def _reload(self) -> bool:
        try:
            self._bridge.reload()
            return True
        except Exception as exc:
            _log.error("engine reload failed: %s", exc)
            return False


def _log_result(result: CategoryResult) -> None:
    if result.outcome is Outcome.UPDATED:
        _log.info(
            "%s: updated (%s domains)", result.name, f"{result.domain_count:,}"
        )
    elif result.outcome is Outcome.UNCHANGED:
        _log.info("%s: unchanged (%s)", result.name, result.message)
    else:
        _log.error("%s: failed — %s", result.name, result.message)
