"""Pink ANSI colouring for the command line (the author is a little pig).

Colour is only emitted to interactive terminals and is suppressed when the
``NO_COLOR`` environment variable is set, so piped/redirected output (cron,
SIEM, ``| grep``) stays clean and parseable.
"""

from __future__ import annotations

import os
from typing import IO

_PINK = "\033[38;5;218m"  # 256-colour soft pink
_BOLD = "\033[1m"
_RESET = "\033[0m"


def use_color(stream: IO[str]) -> bool:
    """True if *stream* is an interactive terminal and colour isn't disabled."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def pink(text: str, stream: IO[str], *, bold: bool = False) -> str:
    """Wrap *text* in pink for *stream*, or return it unchanged if no colour."""
    if not use_color(stream):
        return text
    return f"{_PINK}{_BOLD if bold else ''}{text}{_RESET}"
