"""A small curses category picker for ``egguard select``.

Lets the operator browse the catalogue, toggle which categories to install or
update, and optionally pick an action to apply, as an alternative to naming
categories on the command line. The curses loop only collects a selection; the
caller runs the normal install/update pipeline with it.
"""

from __future__ import annotations

import contextlib
import curses
from dataclasses import dataclass

from .categories import Action, Category
from .state import StateStore

# Actions the picker cycles through; ``None`` leaves it to config/catalogue.
_ACTIONS: tuple[Action | None, ...] = (
    None,
    Action.DENY,
    Action.WARN,
    Action.AUP,
    Action.PERMIT,
)


@dataclass(slots=True)
class Selection:
    """The result of a picker session."""

    names: list[str]
    action: Action | None


def pick(categories: list[Category], store: StateStore) -> Selection | None:
    """Run the curses picker. Return the Selection, or None if cancelled.

    Raises:
        curses.error: if no interactive terminal is available.
    """
    return curses.wrapper(_loop, categories, store)


def action_label(action: Action | None) -> str:
    """Human label for an action choice (``default`` when unset)."""
    return action.value if action is not None else "default"


def format_row(
    category: Category,
    *,
    selected: bool,
    installed: bool,
    action: Action | None,
    cursor: bool,
    name_width: int,
) -> str:
    """Render one catalogue row for the picker (pure, for testing)."""
    pointer = ">" if cursor else " "
    box = "[x]" if selected else "[ ]"
    inst = "*" if installed else " "
    effective = (action or category.disposition).value
    return (
        f"{pointer} {box} {inst} {category.name:<{name_width}}  "
        f"{effective:<7}  {category.description}"
    )


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
            curses.init_color(pink, 1000, 600, 760)  # oink
            foreground = pink
        except curses.error:
            foreground = curses.COLOR_MAGENTA
    curses.init_pair(1, foreground, background)
    return 1


def _loop(
    stdscr: curses.window,
    categories: list[Category],
    store: StateStore,
) -> Selection | None:
    curses.curs_set(0)
    pink = curses.color_pair(_init_pink())
    selected = {c.name for c in categories if store.exists(c.name)}
    name_width = max((len(c.name) for c in categories), default=8)
    action_idx = 0
    cursor = 0
    top = 0

    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        action = _ACTIONS[action_idx]

        _addline(
            stdscr,
            0,
            0,
            "🐷 EGGuard — select categories",
            width,
            pink | curses.A_BOLD,
        )
        _addline(
            stdscr,
            1,
            0,
            "[space] toggle   [a] action   [enter] apply   [q] cancel",
            width,
            pink,
        )

        list_top = 3
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
                action=action,
                cursor=(i == cursor),
                name_width=name_width,
            )
            attr = pink | (curses.A_REVERSE if i == cursor else curses.A_NORMAL)
            _addline(stdscr, list_top + (i - top), 0, row, width, attr)

        footer = (
            f"{len(selected)} selected / {len(categories)}   "
            f"action: {action_label(action)}   oink oink"
        )
        _addline(stdscr, height - 1, 0, footer, width, pink | curses.A_BOLD)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), 27):  # q or ESC
            return None
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
            action_idx = (action_idx + 1) % len(_ACTIONS)
        elif key in (curses.KEY_ENTER, 10, 13):
            names = [c.name for c in categories if c.name in selected]
            return Selection(names=names, action=action)
