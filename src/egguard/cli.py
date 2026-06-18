"""Command-line interface for EGGuard.

Subcommands:
    install     install categories (download, write list/policy, reload)
    update      refresh installed categories to the latest UT1 data
    remove      delete a category's list/policy and reload
    select      pick categories in a curses UI, then install/update them
    list        print the catalogue, marking installed categories
    version     print the EGGuard version
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from . import categories as catalogue
from .categories import Action, Category
from .config import Config, ConfigError
from .engine import EngineBridge, get_bridge
from .fetcher import Fetcher
from .refresh import (
    CategoryResult,
    Refresher,
    RefreshSummary,
    remove_category,
    resolve_action,
    select_categories,
)
from .state import StateStore

if TYPE_CHECKING:
    from .tui import Selection

# Exit codes
EXIT_OK = 0
EXIT_PARTIAL = 1  # some categories failed
EXIT_FATAL = 2  # could not start (bad config, unwritable volume, ...)

_DEFAULT_CONFIG = Path("/var/lib/enforcegate-toolbox/config.yaml")


# Friendly aliases for the four engine actions, accepted by --action.
_ACTION_ALIASES = {"block": Action.DENY, "allow": Action.PERMIT}


def _action_arg(value: str) -> Action:
    """Parse an --action value (an Action name or a friendly alias)."""
    key = value.strip().lower()
    if key in _ACTION_ALIASES:
        return _ACTION_ALIASES[key]
    try:
        return Action(key)
    except ValueError:
        valid = ", ".join(d.value for d in Action)
        raise argparse.ArgumentTypeError(
            f"invalid action {value!r}; expected one of: {valid} "
            f"(aliases: block=deny, allow=permit)"
        ) from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="egguard",
        description="Sync UT1 Capitole blacklist categories into EnforceGate vX.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=_DEFAULT_CONFIG,
        help="path to config.yaml (default: %(default)s)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging"
    )

    sub = parser.add_subparsers(dest="command")

    def add_action(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--action",
            type=_action_arg,
            metavar="ACTION",
            help=(
                "set the action for these categories "
                "(deny|warn|aup|permit; aliases: block=deny, allow=permit)"
            ),
        )

    def add_dry_run(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-n",
            "--dry-run",
            action="store_true",
            help="show what would change, but write/delete nothing",
        )

    install = sub.add_parser(
        "install", help="install categories (download, write, reload)"
    )
    install.add_argument(
        "categories",
        nargs="+",
        metavar="CATEGORY",
        help="categories to install",
    )
    add_action(install)
    add_dry_run(install)

    update = sub.add_parser(
        "update", help="refresh installed categories to the latest data"
    )
    update.add_argument(
        "categories",
        nargs="*",
        metavar="CATEGORY",
        help="categories to update (default: all installed)",
    )
    add_action(update)
    add_dry_run(update)

    remove = sub.add_parser(
        "remove", help="delete a category's list/policy and reload"
    )
    remove.add_argument(
        "categories", nargs="+", metavar="CATEGORY", help="categories to remove"
    )
    add_dry_run(remove)

    select = sub.add_parser(
        "select", help="pick categories in a curses UI, then install/update"
    )
    add_dry_run(select)

    sub.add_parser("list", help="show the catalogue, marking installed")
    sub.add_parser("version", help="print version and exit")
    sub.add_parser("help", help="show this help and exit")

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except BrokenPipeError:
        # A downstream reader (e.g. `head`) closed the pipe. Redirect the
        # remaining stdout to /dev/null so the interpreter's shutdown flush
        # doesn't raise a second BrokenPipeError, then exit quietly.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return EXIT_OK
    except KeyboardInterrupt:
        logging.error("interrupted")
        return EXIT_FATAL


def _run(argv: list[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    # urllib3 logs full request URLs at DEBUG, which would leak the abuse.ch
    # auth key embedded in export URLs; keep it quiet.
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # No subcommand, or the `help` command: show help, do nothing else.
    if args.command in (None, "help"):
        parser.print_help()
        return EXIT_OK

    command = args.command

    try:
        cfg = Config.load(args.config)
    except ConfigError as exc:
        logging.critical("configuration error: %s", exc)
        return EXIT_FATAL

    if command == "version":
        print(f"egguard {__version__}")
        return EXIT_OK
    if command == "list":
        return _cmd_list(cfg)
    if command == "install":
        return _cmd_install(cfg, args)
    if command == "update":
        return _cmd_update(cfg, args)
    if command == "remove":
        return _cmd_remove(cfg, args)
    if command == "select":
        return _cmd_select(cfg, args)

    parser.error(f"unknown command: {command}")


def _current_actions(cfg: Config, store: StateStore) -> dict[str, Action]:
    """Resolve the effective action for every category, reflecting installs."""
    actions: dict[str, Action] = {}
    for category in catalogue.CATALOGUE:
        st = store.load(category.name)
        try:
            installed = Action(st.action) if st.action else None
        except ValueError:
            installed = None
        actions[category.name] = resolve_action(
            category, cfg, installed=installed
        )
    return actions


def _cmd_list(cfg: Config) -> int:
    store = StateStore(cfg.state_dir)
    actions = _current_actions(cfg, store)
    width = max(len(c.name) for c in catalogue.CATALOGUE)
    for category in catalogue.CATALOGUE:
        mark = "*" if store.exists(category.name) else " "
        action = actions[category.name].value
        print(f"{mark} {category.name:<{width}}  {action}")
    print("\n* = installed")
    return EXIT_OK


def _select_named(names: list[str]) -> list[Category]:
    """Look up categories by name; raises KeyError on the first unknown."""
    return [catalogue.get(name) for name in names]


def _actions_for(
    selected: list[Category], action: Action | None
) -> dict[str, Action]:
    """Map every selected category to *action*, or empty when none was given."""
    return {c.name: action for c in selected} if action is not None else {}


def _build_pipeline(
    cfg: Config, *, dry_run: bool
) -> tuple[EngineBridge, Fetcher] | None:
    """Set up the engine bridge and fetcher, or None on a fatal setup error."""
    bridge = get_bridge()
    if not bridge.available and not dry_run:
        logging.warning(
            "enforcegate_toolbox library not found — writing files directly "
            "and skipping engine reload (run inside the toolbox for full operation)"
        )

    # In toolbox mode the helper library owns and provisions the shared
    # lists/rules.d dirs, so only the local fallback needs to create them.
    if not dry_run and not bridge.available:
        for directory in (cfg.lists_dir, cfg.policies_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logging.critical(
                    "cannot create %s: %s — is the enforcegate-shared volume mounted?",
                    directory,
                    exc,
                )
                return None

    fetcher = Fetcher(
        cfg.base_url,
        timeout=cfg.timeout,
        retries=cfg.retries,
        user_agent=cfg.user_agent,
        abusech_base_url=cfg.abusech_base_url,
        abusech_auth_key=cfg.abusech_auth_key,
    )
    return bridge, fetcher


def _report_summary(summary: RefreshSummary, *, dry_run: bool) -> int:
    """Log the dry-run / failure tail of a run and return its exit code."""
    if dry_run:
        logging.info(
            "[dry-run] %d categor%s would change",
            len(summary.updated),
            "y" if len(summary.updated) == 1 else "ies",
        )
    if summary.failed:
        logging.error(
            "%d categor%s failed: %s",
            len(summary.failed),
            "y" if len(summary.failed) == 1 else "ies",
            ", ".join(r.name for r in summary.failed),
        )
        return EXIT_PARTIAL
    return EXIT_OK


def _do_refresh(
    cfg: Config,
    selected: list[Category],
    store: StateStore,
    *,
    actions: dict[str, Action],
    dry_run: bool,
) -> int:
    """Run the fetch/write/reload pipeline for *selected* and return the code."""
    if not selected:
        logging.warning("no categories selected")
        return EXIT_OK

    built = _build_pipeline(cfg, dry_run=dry_run)
    if built is None:
        return EXIT_FATAL
    bridge, fetcher = built

    refresher = Refresher(
        cfg, fetcher, store, bridge, dry_run=dry_run, actions=actions
    )
    summary = refresher.run(selected)
    return _report_summary(summary, dry_run=dry_run)


def _cmd_install(cfg: Config, args: argparse.Namespace) -> int:
    store = StateStore(cfg.state_dir)
    try:
        selected = _select_named(args.categories)
    except KeyError as exc:
        logging.critical("unknown category: %s", exc.args[0])
        return EXIT_FATAL
    return _do_refresh(
        cfg,
        selected,
        store,
        actions=_actions_for(selected, args.action),
        dry_run=args.dry_run,
    )


def _cmd_update(cfg: Config, args: argparse.Namespace) -> int:
    store = StateStore(cfg.state_dir)
    try:
        if args.categories:
            selected = _select_named(args.categories)
        else:
            installed = [n for n in store.installed() if n in catalogue.BY_NAME]
            if installed:
                selected = _select_named(installed)
            else:
                logging.info(
                    "nothing installed yet — updating config-selected categories"
                )
                selected = select_categories(cfg, None)
    except KeyError as exc:
        logging.critical("unknown category: %s", exc.args[0])
        return EXIT_FATAL
    return _do_refresh(
        cfg,
        selected,
        store,
        actions=_actions_for(selected, args.action),
        dry_run=args.dry_run,
    )


def _cmd_remove(cfg: Config, args: argparse.Namespace) -> int:
    store = StateStore(cfg.state_dir)
    try:
        selected = _select_named(args.categories)
    except KeyError as exc:
        logging.critical("unknown category: %s", exc.args[0])
        return EXIT_FATAL

    bridge = get_bridge()
    removed_any = False
    for category in selected:
        if args.dry_run:
            state = (
                "would remove"
                if store.exists(category.name)
                else "not installed"
            )
            logging.info("[dry-run] %s: %s", category.name, state)
            continue
        if remove_category(category, cfg, store, bridge):
            removed_any = True
            logging.info("%s: removed", category.name)
        else:
            logging.info("%s: not installed", category.name)

    if removed_any:
        try:
            bridge.reload()
        except Exception as exc:
            logging.error("engine reload failed: %s", exc)
            return EXIT_PARTIAL
    return EXIT_OK


def _status_line(result: CategoryResult) -> str:
    """One per-category status line for the picker, from the run result."""
    mark = {"updated": "+", "unchanged": "=", "failed": "!"}.get(
        result.outcome.value, " "
    )
    if result.outcome.value == "updated":
        detail = f" ({result.domain_count} domains)"
    elif result.outcome.value == "failed":
        detail = f": {result.message}"
    else:
        detail = ""
    return f"{mark} {result.name}  {result.outcome.value}{detail}"


def _summary_line(summary: RefreshSummary, *, dry_run: bool) -> str:
    """A short one-line summary of a run, for the picker's done screen."""
    unchanged = (
        len(summary.results) - len(summary.updated) - len(summary.failed)
    )
    if dry_run:
        note = "dry run (nothing written)"
    elif summary.reloaded:
        note = "engine reloaded"
    elif summary.changed:
        note = "engine NOT reloaded"
    else:
        note = "no changes"
    return (
        f"{len(summary.updated)} updated, {unchanged} unchanged, "
        f"{len(summary.failed)} failed | {note}"
    )


def _cmd_select(cfg: Config, args: argparse.Namespace) -> int:
    import curses

    from . import tui

    store = StateStore(cfg.state_dir)
    summary_box: list[RefreshSummary] = []

    def installer(
        selection: Selection, progress: Callable[[int, int, str], None]
    ) -> str:
        built = _build_pipeline(cfg, dry_run=args.dry_run)
        if built is None:
            return "setup failed"
        bridge, fetcher = built
        refresher = Refresher(
            cfg,
            fetcher,
            store,
            bridge,
            dry_run=args.dry_run,
            actions=selection.actions,
        )

        def on_progress(done: int, total: int, result: CategoryResult) -> None:
            progress(done, total, _status_line(result))

        summary = refresher.run(
            _select_named(selection.names), on_progress=on_progress, quiet=True
        )
        summary_box.append(summary)
        return _summary_line(summary, dry_run=args.dry_run)

    current = _current_actions(cfg, store)
    try:
        applied = tui.pick(list(catalogue.CATALOGUE), store, installer, current)
    except curses.error as exc:
        logging.critical(
            "cannot open the selector (no interactive terminal?): %s", exc
        )
        return EXIT_FATAL

    if not applied:
        logging.info("nothing selected")
        return EXIT_OK
    if not summary_box:
        return EXIT_FATAL
    return _report_summary(summary_box[0], dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
