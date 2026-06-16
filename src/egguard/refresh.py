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
from dataclasses import dataclass, field
from enum import Enum

from . import categories as catalogue
from .categories import Category, Disposition
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


def resolve_action(category: Category, cfg: Config) -> Disposition:
    """Resolve the action for *category*: override > default > suggestion."""
    if category.name in cfg.actions:
        return cfg.actions[category.name]
    if cfg.default_action is not None:
        return cfg.default_action
    return category.disposition


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
    ) -> None:
        self._cfg = cfg
        self._fetcher = fetcher
        self._store = store
        self._bridge = bridge
        self._dry_run = dry_run

    def run(self, selected: list[Category]) -> RefreshSummary:
        """Refresh every category in *selected* and reload once if needed."""
        summary = RefreshSummary()
        started = time.monotonic()

        for category in selected:
            result = self._refresh_one(category)
            summary.results.append(result)
            _log_result(result)

        summary.elapsed_seconds = time.monotonic() - started

        if summary.changed and not self._dry_run:
            summary.reloaded = self._reload()

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

        if not self._dry_run:
            self._write(category, domains)
            self._store.save(
                category.name,
                CategoryState(
                    etag=fetched.etag,
                    last_modified=fetched.last_modified,
                    sha256=sha256,
                    domain_count=len(domains),
                ),
            )

        return CategoryResult(category.name, Outcome.UPDATED, len(domains))

    def _write(self, category: Category, domains: list[str]) -> None:
        list_path = self._cfg.lists_dir / category.list_filename
        policy_path = self._cfg.policies_dir / category.policy_filename(
            self._cfg.policy_prefix
        )
        action = resolve_action(category, self._cfg)

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
