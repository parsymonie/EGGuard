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
from collections.abc import Callable
from dataclasses import dataclass, field

from .categories import Action, Category
from .state import StateStore

# Per-category actions are cycled with the `a` key; ``None`` leaves the action
# to config/catalogue resolution.
_ACTIONS: tuple[Action | None, ...] = (
    None,
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


# Runs the actual install for a selection, reporting progress as it goes.
Installer = Callable[["Selection", ProgressFn], None]


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


def progress_bar(done: int, total: int, width: int) -> str:
    """Render a text progress bar like ``[####----]  50%`` (pure, for testing)."""
    width = max(1, width)
    ratio = 1.0 if total <= 0 else max(0.0, min(1.0, done / total))
    filled = int(ratio * width)
    return (
        "["
        + "#" * filled
        + "-" * (width - filled)
        + f"] {int(ratio * 100):3d}%"
    )


def _cycle_action(current: Action | None) -> Action | None:
    """Return the next action in the cycle after *current*."""
    return _ACTIONS[(_ACTIONS.index(current) + 1) % len(_ACTIONS)]


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


def _run_install(
    stdscr: curses.window,
    pink: int,
    selection: Selection,
    installer: Installer,
) -> None:
    """Drive the install in place, drawing a progress bar after each category."""
    total = len(selection.names)

    def report(done: int, total_: int, message: str) -> None:
        stdscr.erase()
        _height, width = stdscr.getmaxyx()
        _addline(
            stdscr,
            0,
            0,
            "Installing selected categories",
            width,
            pink | curses.A_BOLD,
        )
        bar = progress_bar(done, total_, max(10, width - 8))
        _addline(stdscr, 2, 0, bar, width, pink)
        _addline(stdscr, 3, 0, f"{done}/{total_}  {message}", width, pink)
        stdscr.refresh()

    report(0, total, "starting...")
    installer(selection, report)

    stdscr.erase()
    _height, width = stdscr.getmaxyx()
    _addline(stdscr, 0, 0, "Done. Press any key.", width, pink | curses.A_BOLD)
    _addline(
        stdscr,
        2,
        0,
        progress_bar(total, total, max(10, width - 8)),
        width,
        pink,
    )
    stdscr.refresh()
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
            # Cycle the action for this row only.
            name = categories[cursor].name
            nxt = _cycle_action(chosen.get(name))
            if nxt is None:
                chosen.pop(name, None)
            else:
                chosen[name] = nxt
        elif key in (curses.KEY_ENTER, 10, 13):
            names = [c.name for c in categories if c.name in selected]
            if not names:
                return False
            actions = {n: chosen[n] for n in names if n in chosen}
            _run_install(
                stdscr, pink, Selection(names=names, actions=actions), installer
            )
            return True
