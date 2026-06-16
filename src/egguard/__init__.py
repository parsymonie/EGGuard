"""EgGuard — sync UT1 Capitole blacklist categories into EnforceGate vX.

EgGuard runs inside the EnforceGate vX toolbox sidecar. It downloads the
Université Toulouse Capitole blacklist categories, converts each into an
EnforceGate domain list and a matching ``.policy`` rule, and triggers a
single engine reload.

Upstream data: https://dsi.ut-capitole.fr/blacklists/  (CC BY-SA 4.0)
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "parsymonie"
__url__ = "https://github.com/parsymonie/egguard"
__all__ = ["__version__"]
