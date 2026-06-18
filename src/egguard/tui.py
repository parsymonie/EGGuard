"""A small curses category picker for ``egguard select``.

Lets the operator browse the catalogue, toggle which categories to install or
update, and set a per-category action, then runs the install in place with a
progress bar (so the whole flow stays inside the curses UI). It is an
alternative to naming categories on the command line.
"""

from __future__ import annotations

import contextlib
import curses
import io
import locale
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from .categories import Action, Category, source_label
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
    r"   |  (..) |     category picker for EnforceGate vX (UT1 + abuse.ch)",
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
    source_width: int = 0,
) -> str:
    """Render one catalogue row for the picker (pure, for testing).

    *action* is the operator's per-row override (or None); *default_action* is
    the action currently in effect, shown when there is no override.
    *source_width* (>0) adds a source column so multi-source feeds (UT1,
    abuse.ch) are distinguishable.
    """
    pointer = ">" if cursor else " "
    box = "[x]" if selected else "[ ]"
    inst = "*" if installed else " "
    effective = (action or default_action).value
    src = (
        f"{source_label(category.source):<{source_width}}  "
        if source_width
        else ""
    )
    return (
        f"{pointer} {box} {inst} {src}{category.name:<{name_width}}  "
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


@dataclass(frozen=True, slots=True)
class Palette:
    """Pink colour attributes for the picker, one shade per UX role.

    Each field is a ready-to-use curses attribute (colour pair OR'd with any
    style bits), so callers pass it straight to ``addnstr``.
    """

    art: int  # the pig header — brightest pink
    text: int  # primary text (category names)
    muted: int  # secondary text (descriptions, instructions, unchanged)
    source: int  # the source column / AUP action
    action: int  # the action column / WARN / "updated"
    accent: int  # headers, selection, deny, summary — the strongest pink


# Role -> (xterm-256 pink index, redefinable-palette RGB on a 0..1000 scale).
# We prefer real RGB when the terminal allows it, fall back to the fixed
# xterm-256 pinks on 256-colour terminals, and to magenta+styles otherwise.
_PINK_ROLES: tuple[tuple[str, int, tuple[int, int, int]], ...] = (
    ("art", 218, (1000, 686, 843)),  # light pink
    ("text", 211, (1000, 529, 686)),  # pink
    ("muted", 175, (843, 529, 686)),  # dusty rose
    ("source", 213, (1000, 529, 1000)),  # orchid pink
    ("action", 205, (1000, 372, 686)),  # hot pink
    ("accent", 198, (1000, 60, 529)),  # deep pink
)


def _init_palette() -> Palette:
    """Set up the pink palette and return its per-role attributes.

    The author is a little pig, so the picker is pink — but in several shades
    so columns and components are easy to tell apart. Degrades gracefully:
    redefinable RGB where available, the fixed xterm-256 pinks on 256-colour
    terminals, then magenta with style bits, then plain styles with no colour.
    """
    if not curses.has_colors():
        # No colour at all: lean on bold/dim so roles still differ a little.
        return Palette(
            art=curses.A_BOLD,
            text=curses.A_NORMAL,
            muted=curses.A_DIM,
            source=curses.A_NORMAL,
            action=curses.A_BOLD,
            accent=curses.A_BOLD | curses.A_REVERSE,
        )

    curses.start_color()
    try:
        curses.use_default_colors()
        background = -1
    except curses.error:
        background = curses.COLOR_BLACK

    can_custom = curses.can_change_color() and curses.COLORS > 16
    attrs: dict[str, int] = {}
    for i, (role, idx, rgb) in enumerate(_PINK_ROLES, start=1):
        foreground = curses.COLOR_MAGENTA
        if can_custom:
            color_id = min(curses.COLORS - 1, 200 + i)
            try:
                curses.init_color(color_id, *rgb)
                foreground = color_id
            except curses.error:
                foreground = idx if curses.COLORS >= 256 else foreground
        elif curses.COLORS >= 256:
            foreground = idx
        try:
            curses.init_pair(i, foreground, background)
            attrs[role] = curses.color_pair(i)
        except curses.error:
            attrs[role] = 0

    # Add a little weight to the prominent roles so they stand out even when
    # the terminal collapsed several shades onto the same magenta.
    return Palette(
        art=attrs["art"] | curses.A_BOLD,
        text=attrs["text"],
        muted=attrs["muted"],
        source=attrs["source"],
        action=attrs["action"] | curses.A_BOLD,
        accent=attrs["accent"] | curses.A_BOLD,
    )


def _action_attr(action: Action, palette: Palette) -> int:
    """Pick a shade for an action so deny/warn/aup/permit read differently."""
    return {
        Action.DENY: palette.accent,
        Action.WARN: palette.action,
        Action.AUP: palette.source,
        Action.PERMIT: palette.muted,
    }.get(action, palette.text)


def _draw_segments(
    stdscr: curses.window, y: int, x: int, segments: list[tuple[str, int]]
) -> None:
    """Draw coloured (text, attr) segments left to right from *x*."""
    for text, attr in segments:
        _addstr(stdscr, y, x, text, attr)
        x += len(text)


def _status_attr(line: str, palette: Palette) -> int:
    """Colour a per-category status line by its leading mark (+/=/!)."""
    mark = line[:1]
    if mark == "!":
        return palette.accent  # failure — strongest
    if mark == "+":
        return palette.action  # updated
    if mark == "=":
        return palette.muted  # unchanged
    return palette.text


def _draw_progress(
    stdscr: curses.window,
    palette: Palette,
    done: int,
    total: int,
    log: list[str],
    *,
    summary: str,
    finished: bool,
) -> None:
    """Draw the art header, a reverse-video bar, and the per-category status."""
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    bar_w = min(48, max(10, width - 12))
    ratio = 1.0 if total <= 0 else max(0.0, min(1.0, done / total))
    filled = bar_fill(done, total, bar_w)
    left = 2

    # Keep the same pig header as the picker.
    for idx, line in enumerate(_ART):
        _addline(stdscr, idx, 0, line, width, palette.art)
    top = len(_ART)

    title = "Done. Press any key." if finished else "Installing categories..."
    _addstr(stdscr, top, left, title, palette.accent)

    # [ <filled: reverse-video> <empty> ]  NN%
    bar_row = top + 2
    _addstr(stdscr, bar_row, left, "[", palette.text)
    _addstr(
        stdscr,
        bar_row,
        left + 1,
        " " * filled,
        palette.action | curses.A_REVERSE,
    )
    _addstr(
        stdscr,
        bar_row,
        left + 1 + filled,
        " " * (bar_w - filled),
        palette.muted,
    )
    _addstr(stdscr, bar_row, left + 1 + bar_w, "]", palette.text)
    _addstr(
        stdscr,
        bar_row,
        left + 3 + bar_w,
        f"{int(ratio * 100):3d}%",
        palette.accent,
    )
    _addstr(
        stdscr, bar_row + 1, left, f"{done}/{total} categories", palette.text
    )

    # The per-category status from the engine/client API, newest at the bottom.
    log_top = bar_row + 3
    reserve = 2 if (finished and summary) else 0
    avail = max(0, height - log_top - reserve)
    for i, line in enumerate(log[-avail:] if avail else []):
        _addstr(stdscr, log_top + i, left, line, _status_attr(line, palette))

    if finished and summary:
        _addstr(stdscr, height - 2, left, summary, palette.accent)

    stdscr.refresh()


def _run_install(
    stdscr: curses.window,
    palette: Palette,
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
            stdscr, palette, done, total_, log, summary="", finished=False
        )

    report(0, total, "")
    # Curses draws via the C-level terminal, so keep the install's output off
    # the screen on every layer: disable Python logging, swap sys.stdout/stderr
    # (catches the toolbox library's print-style writes), and redirect the
    # stderr fd for anything C-level.
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved_stderr_fd = os.dup(2)
    saved_out, saved_err = sys.stdout, sys.stderr
    logging.disable(logging.CRITICAL)
    try:
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        os.dup2(devnull, 2)
        summary = installer(selection, report)
    finally:
        logging.disable(logging.NOTSET)
        sys.stdout, sys.stderr = saved_out, saved_err
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stderr_fd)
        os.close(devnull)

    _draw_progress(
        stdscr, palette, total, total, log, summary=summary, finished=True
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
    palette = _init_palette()
    selected = {c.name for c in categories if store.exists(c.name)}
    chosen: dict[str, Action] = {}
    name_width = max((len(c.name) for c in categories), default=8)
    # Only show a source column when more than one source is present.
    sources = {c.source for c in categories}
    source_width = (
        max(len(source_label(c.source)) for c in categories)
        if len(sources) > 1
        else 0
    )
    cursor = 0
    top = 0

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()

        for idx, line in enumerate(_ART):
            _addline(stdscr, idx, 0, line, width, palette.art)
        instr_row = len(_ART)
        _addline(
            stdscr,
            instr_row,
            0,
            "[space] toggle   [a] action (this row)   [enter] install   [q] cancel",
            width,
            palette.muted,
        )

        # Column header on the row between the instructions and the list, each
        # label in its column's colour so the shades double as a legend (the
        # 8-char indent lines up with format_row's marker columns).
        if source_width:
            header_segs: list[tuple[str, int]] = [
                (" " * 8, palette.text),
                (
                    f"{'SOURCE':<{source_width}}  ",
                    palette.source | curses.A_BOLD,
                ),
                (f"{'CATEGORY':<{name_width}}  ", palette.text | curses.A_BOLD),
                ("ACTION", palette.action | curses.A_BOLD),
            ]
            _draw_segments(stdscr, instr_row + 1, 0, header_segs)

        list_top = instr_row + 2
        visible = max(1, height - list_top - 1)
        if cursor < top:
            top = cursor
        elif cursor >= top + visible:
            top = cursor - visible + 1

        for i in range(top, min(top + visible, len(categories))):
            category = categories[i]
            is_selected = category.name in selected
            is_installed = store.exists(category.name)
            effective = chosen.get(category.name) or current_actions.get(
                category.name, category.disposition
            )
            row_y = list_top + (i - top)
            if i == cursor:
                # The focused row is one solid highlighted bar.
                row = format_row(
                    category,
                    selected=is_selected,
                    installed=is_installed,
                    action=chosen.get(category.name),
                    default_action=current_actions.get(
                        category.name, category.disposition
                    ),
                    cursor=True,
                    name_width=name_width,
                    source_width=source_width,
                )
                _addline(
                    stdscr,
                    row_y,
                    0,
                    row,
                    width,
                    palette.accent | curses.A_REVERSE,
                )
                continue
            segs: list[tuple[str, int]] = [
                ("  ", palette.text),  # cursor column (blank when not focused)
                (
                    f"{'[x]' if is_selected else '[ ]'} ",
                    palette.accent if is_selected else palette.muted,
                ),
                (
                    f"{'*' if is_installed else ' '} ",
                    palette.action if is_installed else palette.text,
                ),
            ]
            if source_width:
                segs.append(
                    (
                        f"{source_label(category.source):<{source_width}}  ",
                        palette.source,
                    )
                )
            segs.append((f"{category.name:<{name_width}}  ", palette.text))
            segs.append(
                (f"{effective.value:<7}  ", _action_attr(effective, palette))
            )
            segs.append((category.description, palette.muted))
            _draw_segments(stdscr, row_y, 0, segs)

        footer = f"{len(selected)} selected / {len(categories)}"
        _addline(stdscr, height - 1, 0, footer, width, palette.accent)
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
                stdscr,
                palette,
                Selection(names=names, actions=actions),
                installer,
            )
            return True
