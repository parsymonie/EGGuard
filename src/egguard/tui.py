"""A small curses category picker for ``egguard select``.

Lets the operator browse the catalogue, toggle which categories to install or
update, and set a per-category action, then runs the install in place with a
progress bar (so the whole flow stays inside the curses UI). It is an
alternative to naming categories on the command line.
"""

from __future__ import annotations

import contextlib
import curses
import locale
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from .categories import Action, Category
from .state import StateStore

# The `a` key cycles through the four real actions, starting from whatever is
# currently in effect for the row.
_CYCLE: tuple[Action, ...] = (
    Action.DENY,
    Action.WARN,
    Action.AUP,
    Action.PERMIT,
)

# A little pig with a curly tail, pure ASCII so it renders everywhere.
_ART: tuple[str, ...] = (
    r"     _____",
    r"    /     \,~~",
    r"   | o   o |     E G G u a r d",
    r"   |  (..) |     UT1 category picker for EnforceGate vX",
    r"    \_____/",
    r"     ''  ''",
)

# A progress reporter: (done, total, message).
ProgressFn = Callable[[int, int, str], None]


@dataclass(slots=True)
class Selection:
    """What the picker chose: which categories, and any per-category actions."""

    names: list[str]
    actions: dict[str, Action] = field(default_factory=dict)


# Runs the install for a selection, reporting progress as it goes and returning
# a short human summary (e.g. "4 updated, 0 unchanged | engine reloaded").
Installer = Callable[["Selection", ProgressFn], str]


def pick(
    categories: list[Category],
    store: StateStore,
    installer: Installer,
    current_actions: dict[str, Action],
) -> bool:
    """Run the picker and, on confirm, install the selection in place.

    *current_actions* maps each category to the action currently in effect
    (reflecting installed policies and config), shown until the operator
    overrides it with ``a``.

    Returns True if an install was applied, False if cancelled or nothing was
    chosen.

    Raises:
        curses.error: if no interactive terminal is available.
    """
    # Honour the terminal's encoding so accented descriptions render.
    locale.setlocale(locale.LC_ALL, "")
    return bool(
        curses.wrapper(_loop, categories, store, installer, current_actions)
    )


def action_label(action: Action | None) -> str:
    """Human label for an action choice (``default`` when unset)."""
    return action.value if action is not None else "default"


def format_row(
    category: Category,
    *,
    selected: bool,
    installed: bool,
    action: Action | None,
    default_action: Action,
    cursor: bool,
    name_width: int,
) -> str:
    """Render one catalogue row for the picker (pure, for testing).

    *action* is the operator's per-row override (or None); *default_action* is
    the action currently in effect, shown when there is no override.
    """
    pointer = ">" if cursor else " "
    box = "[x]" if selected else "[ ]"
    inst = "*" if installed else " "
    effective = (action or default_action).value
    return (
        f"{pointer} {box} {inst} {category.name:<{name_width}}  "
        f"{effective:<7}  {category.description}"
    )


def bar_fill(done: int, total: int, width: int) -> int:
    """Filled-cell count for a *width*-cell progress bar (pure, for testing)."""
    if width <= 0:
        return 0
    ratio = 1.0 if total <= 0 else max(0.0, min(1.0, done / total))
    return round(ratio * width)


def _cycle_action(current: Action) -> Action:
    """Return the next action after *current* (deny -> warn -> aup -> permit)."""
    return _CYCLE[(_CYCLE.index(current) + 1) % len(_CYCLE)]


def _addline(
    stdscr: curses.window,
    y: int,
    x: int,
    text: str,
    width: int,
    attr: int = 0,
) -> None:
    """Draw one clamped line, ignoring harmless edge-of-screen errors."""
    if y < 0:
        return
    with contextlib.suppress(curses.error):
        stdscr.addnstr(y, x, text, max(0, width - 1), attr)


def _addstr(
    stdscr: curses.window, y: int, x: int, text: str, attr: int
) -> None:
    """Draw *text* at (y, x), clamped to the screen, ignoring edge errors."""
    if y < 0 or x < 0:
        return
    _height, width = stdscr.getmaxyx()
    if x >= width:
        return
    with contextlib.suppress(curses.error):
        stdscr.addnstr(y, x, text, max(0, width - x - 1), attr)


def _init_pink() -> int:
    """Set up a pink colour pair and return it (0 = terminal has no colour).

    The author is a little pig, so the picker is pink. Real pink needs a
    redefinable palette; otherwise we fall back to the nearest stock colour
    (magenta).
    """
    if not curses.has_colors():
        return 0
    curses.start_color()
    try:
        curses.use_default_colors()
        background = -1
    except curses.error:
        background = curses.COLOR_BLACK
    foreground = curses.COLOR_MAGENTA
    if curses.can_change_color() and curses.COLORS > 16:
        pink = min(curses.COLORS - 1, 200)
        try:
            curses.init_color(pink, 1000, 600, 760)
            foreground = pink
        except curses.error:
            foreground = curses.COLOR_MAGENTA
    curses.init_pair(1, foreground, background)
    return 1


def _draw_progress(
    stdscr: curses.window,
    pink: int,
    done: int,
    total: int,
    log: list[str],
    *,
    summary: str,
    finished: bool,
) -> None:
    """Draw a reverse-video bar plus the per-category status returned so far."""
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    bar_w = min(48, max(10, width - 12))
    ratio = 1.0 if total <= 0 else max(0.0, min(1.0, done / total))
    filled = bar_fill(done, total, bar_w)
    left = max(0, (width - bar_w - 7) // 2)

    title = "Done. Press any key." if finished else "Installing categories..."
    _addstr(stdscr, 0, left, title, pink | curses.A_BOLD)

    # [ <filled: reverse-video> <empty> ]  NN%
    _addstr(stdscr, 2, left, "[", pink)
    _addstr(stdscr, 2, left + 1, " " * filled, pink | curses.A_REVERSE)
    _addstr(stdscr, 2, left + 1 + filled, " " * (bar_w - filled), pink)
    _addstr(stdscr, 2, left + 1 + bar_w, "]", pink)
    _addstr(
        stdscr,
        2,
        left + 3 + bar_w,
        f"{int(ratio * 100):3d}%",
        pink | curses.A_BOLD,
    )
    _addstr(stdscr, 3, left, f"{done}/{total} categories", pink)

    # The per-category status from the engine/client API, newest at the bottom.
    log_top = 5
    reserve = 2 if (finished and summary) else 0
    avail = max(0, height - log_top - reserve)
    for i, line in enumerate(log[-avail:] if avail else []):
        _addstr(stdscr, log_top + i, 2, line, pink)

    if finished and summary:
        _addstr(stdscr, height - 2, 2, summary, pink | curses.A_BOLD)

    stdscr.refresh()


def _run_install(
    stdscr: curses.window,
    pink: int,
    selection: Selection,
    installer: Installer,
) -> None:
    """Run the install in place, showing live per-category status."""
    total = len(selection.names)
    log: list[str] = []

    def report(done: int, total_: int, message: str) -> None:
        if done >= 1:
            log.append(message)
        _draw_progress(
            stdscr, pink, done, total_, log, summary="", finished=False
        )

    report(0, total, "")
    # Curses owns the screen, so keep the install's output off it: disable all
    # Python logging (EGGuard's own and the toolbox library's structured logs,
    # whatever stream they target) and redirect stray stderr to /dev/null.
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved_stderr = os.dup(2)
    logging.disable(logging.CRITICAL)
    try:
        os.dup2(devnull, 2)
        summary = installer(selection, report)
    finally:
        logging.disable(logging.NOTSET)
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)
        os.close(devnull)

    _draw_progress(
        stdscr, pink, total, total, log, summary=summary, finished=True
    )
    stdscr.getch()


def _loop(
    stdscr: curses.window,
    categories: list[Category],
    store: StateStore,
    installer: Installer,
    current_actions: dict[str, Action],
) -> bool:
    curses.curs_set(0)
    pink = curses.color_pair(_init_pink())
    selected = {c.name for c in categories if store.exists(c.name)}
    chosen: dict[str, Action] = {}
    name_width = max((len(c.name) for c in categories), default=8)
    cursor = 0
    top = 0

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()

        for idx, line in enumerate(_ART):
            _addline(stdscr, idx, 0, line, width, pink | curses.A_BOLD)
        instr_row = len(_ART)
        _addline(
            stdscr,
            instr_row,
            0,
            "[space] toggle   [a] action (this row)   [enter] install   [q] cancel",
            width,
            pink,
        )

        list_top = instr_row + 2
        visible = max(1, height - list_top - 1)
        if cursor < top:
            top = cursor
        elif cursor >= top + visible:
            top = cursor - visible + 1

        for i in range(top, min(top + visible, len(categories))):
            category = categories[i]
            row = format_row(
                category,
                selected=category.name in selected,
                installed=store.exists(category.name),
                action=chosen.get(category.name),
                default_action=current_actions.get(
                    category.name, category.disposition
                ),
                cursor=(i == cursor),
                name_width=name_width,
            )
            attr = pink | (curses.A_REVERSE if i == cursor else curses.A_NORMAL)
            _addline(stdscr, list_top + (i - top), 0, row, width, attr)

        footer = f"{len(selected)} selected / {len(categories)}"
        _addline(stdscr, height - 1, 0, footer, width, pink | curses.A_BOLD)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), 27):  # q or ESC
            return False
        if key in (curses.KEY_UP, ord("k")):
            cursor = max(0, cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor = min(len(categories) - 1, cursor + 1)
        elif key == curses.KEY_NPAGE:
            cursor = min(len(categories) - 1, cursor + visible)
        elif key == curses.KEY_PPAGE:
            cursor = max(0, cursor - visible)
        elif key == curses.KEY_HOME:
            cursor = 0
        elif key == curses.KEY_END:
            cursor = len(categories) - 1
        elif key == ord(" "):
            name = categories[cursor].name
            if name in selected:
                selected.discard(name)
            else:
                selected.add(name)
        elif key in (ord("a"), ord("A")):
            # Cycle the action for this row, starting from what's in effect so
            # the first press always advances visibly.
            category = categories[cursor]
            current = chosen.get(category.name) or current_actions.get(
                category.name, category.disposition
            )
            chosen[category.name] = _cycle_action(current)
        elif key in (curses.KEY_ENTER, 10, 13):
            names = [c.name for c in categories if c.name in selected]
            if not names:
                return False
            actions = {n: chosen[n] for n in names if n in chosen}
            _run_install(
                stdscr, pink, Selection(names=names, actions=actions), installer
            )
            return True
