"""EGGuard — sync UT1 Capitole blacklist categories into EnforceGate vX.

EGGuard runs inside the EnforceGate vX toolbox sidecar. It downloads the
Université Toulouse Capitole blacklist categories, converts each into an
EnforceGate domain list and a matching ``.policy`` rule, and triggers a
single engine reload.

It can be driven two ways:

* **As a CLI / cron job** — ``egguard install`` / ``egguard update`` (see
  ``egguard --help``).
* **As a library** — import the building blocks to automate list and policy
  creation for a category::

      from pathlib import Path
      from egguard import Action, get, extract_domains, render_policy

      category = get("gambling")
      domains = extract_domains(tarball_bytes)          # normalised hosts
      policy = render_policy(
          category,
          list_path=Path("/etc/enforcegate-shared/lists/ut1-gambling.list"),
          action=Action.DENY,
      )

  Or fetch + write a whole run with :class:`Refresher` / :class:`Fetcher`.

Upstream data: https://dsi.ut-capitole.fr/blacklists/  (CC BY-SA 4.0)
"""

from __future__ import annotations

from .categories import CATALOGUE, Action, Category, all_names, get
from .config import Config, ConfigError
from .engine import EngineBridge, get_bridge
from .fetcher import Fetcher, FetchError, FetchResult, NotModified
from .parser import ParseError, extract_domains
from .policy import render_policy
from .refresh import (
    CategoryResult,
    Outcome,
    Refresher,
    RefreshSummary,
    resolve_action,
    select_categories,
)
from .state import CategoryState, StateStore

__version__ = "1.0.0"
__author__ = "parsymonie"
__url__ = "https://github.com/parsymonie/egguard"

__all__ = [
    "CATALOGUE",
    "Action",
    "Category",
    "CategoryResult",
    "CategoryState",
    "Config",
    "ConfigError",
    "EngineBridge",
    "FetchError",
    "FetchResult",
    "Fetcher",
    "NotModified",
    "Outcome",
    "ParseError",
    "RefreshSummary",
    "Refresher",
    "StateStore",
    "__version__",
    "all_names",
    "extract_domains",
    "get",
    "get_bridge",
    "render_policy",
    "resolve_action",
    "select_categories",
]
