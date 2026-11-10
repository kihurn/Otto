"""Otto's named actions. Nothing else can touch the computer.

Each action has a fixed name, typed parameters, a risk level, and a plain-English description used
when Otto asks you to confirm. The brain and recipes can only use actions from this list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

READ, UNDOABLE, ASK = 0, 1, 2
RISK_NAMES = {READ: "read", UNDOABLE: "undoable", ASK: "ask first"}


@dataclass
class Result:
    ok: bool
    say: str
    data: dict = field(default_factory=dict)


@dataclass
class Action:
    name: str
    fn: Callable[..., Result]
    risk: int
    params: dict[str, str]              # name -> short description
    describe: Callable[..., str]        # used for "Shall I ...?"
    for_brain: bool = False             # may the brain use it in new plans?
    note: str = ""                      # hint for the brain


ACTIONS: dict[str, Action] = {}


def action(name: str, risk: int, params: dict[str, str], describe: Callable[..., str],
           for_brain: bool = False, note: str = ""):
    def wrap(fn):
        ACTIONS[name] = Action(name, fn, risk, params, describe, for_brain, note)
        return fn
    return wrap


def brain_menu() -> str:
    """The list of building blocks the brain may plan with."""
    lines = []
    for a in ACTIONS.values():
        if a.for_brain:
            ps = ", ".join(f"{k}: {v}" for k, v in a.params.items()) or "no parameters"
            lines.append(f"- {a.name}({ps})" + (f"  # {a.note}" if a.note else ""))
    return "\n".join(lines)


def load_all() -> None:
    """Import every hands module so their actions register themselves."""
    from hands import apps, files, media, notes, timers, web  # noqa: F401
