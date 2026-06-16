"""Command-line interface for EGGuard.

Subcommands:
    refresh     download categories, write lists/policies, reload engine
    list        print the category catalogue and resolved actions
    version     print the EGGuard version
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import __version__
from . import categories as catalogue
from .config import Config, ConfigError
from .engine import get_bridge
from .fetcher import Fetcher
from .refresh import Refresher, resolve_action, select_categories
from .state import StateStore

# Exit codes
EXIT_OK = 0
EXIT_PARTIAL = 1  # some categories failed
EXIT_FATAL = 2  # could not start (bad config, unwritable volume, ...)

_DEFAULT_CONFIG = Path("/var/lib/enforcegate-toolbox/config.yaml")


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

    refresh = sub.add_parser("refresh", help="download and install categories")
    refresh.add_argument(
        "-C",
        "--category",
        action="append",
        dest="categories",
        metavar="NAME",
        help="refresh only this category (repeatable; overrides config selection)",
    )
    refresh.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="download and parse, but write nothing and do not reload",
    )

    sub.add_parser(
        "list", help="show the category catalogue and resolved actions"
    )
    sub.add_parser("version", help="print version and exit")

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

    # Default to 'refresh' when no subcommand is given.
    command = args.command or "refresh"

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
    if command == "refresh":
        return _cmd_refresh(cfg, args)

    parser.error(f"unknown command: {command}")


def _cmd_list(cfg: Config) -> int:
    width = max(len(c.name) for c in catalogue.CATALOGUE)
    for category in catalogue.CATALOGUE:
        action = resolve_action(category, cfg)
        print(
            f"{category.name:<{width}}  {action.value:<7}  {category.description}"
        )
    return EXIT_OK


def _cmd_refresh(cfg: Config, args: argparse.Namespace) -> int:
    dry_run: bool = args.dry_run

    # Resolve categories early so a typo fails fast.
    try:
        selected = select_categories(cfg, args.categories)
    except KeyError as exc:
        logging.critical("unknown category: %s", exc.args[0])
        return EXIT_FATAL

    if not selected:
        logging.warning("no categories selected — check include/skip in config")
        return EXIT_OK

    # Ensure output directories exist (unless dry-run).
    if not dry_run:
        for directory in (cfg.lists_dir, cfg.policies_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logging.critical(
                    "cannot create %s: %s — is the enforcegate-shared volume mounted?",
                    directory,
                    exc,
                )
                return EXIT_FATAL

    bridge = get_bridge()
    if not bridge.available and not dry_run:
        logging.warning(
            "enforcegate_toolbox library not found — writing files directly "
            "and skipping engine reload (run inside the toolbox for full operation)"
        )

    fetcher = Fetcher(
        cfg.base_url,
        timeout=cfg.timeout,
        retries=cfg.retries,
        user_agent=cfg.user_agent,
    )
    store = StateStore(cfg.state_dir)
    refresher = Refresher(cfg, fetcher, store, bridge, dry_run=dry_run)

    summary = refresher.run(selected)

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


if __name__ == "__main__":
    sys.exit(main())
