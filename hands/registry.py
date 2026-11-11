"""Otto's named actions. Nothing else can touch the computer.

Each action has a fixed name, typed parameters, a risk level, and a plain-English description used
when Otto asks you to confirm. The brain and recipes can only use actions from this list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
import inspect
import math
import re

from core.tasks import Outcome, OutcomeStatus

READ, UNDOABLE, ASK = 0, 1, 2
RISK_NAMES = {READ: "read", UNDOABLE: "undoable", ASK: "ask first"}


@dataclass
class Result:
    ok: bool
    say: str
    data: dict = field(default_factory=dict)

    def to_outcome(self, *, dry_run: bool = False) -> Outcome:
        """Legacy acceptance is not observation evidence. Never infer verified success."""
        status = (OutcomeStatus.FAILED if not self.ok else
                  OutcomeStatus.SIMULATED if dry_run else OutcomeStatus.DISPATCHED)
        return Outcome(status, self.say, dict(self.data), side_effect_possible=not dry_run)


class InvalidPlan(ValueError):
    """A plan failed validation before any action was run."""


def validate_args(a: "Action", args: dict) -> None:
    if not isinstance(args, dict) or any(not isinstance(k, str) for k in args):
        raise InvalidPlan("Action arguments must be a JSON object.")
    if set(args) - set(a.params):
        raise InvalidPlan(f"Unknown argument for {a.name}.")
    try:
        inspect.signature(a.fn).bind(**args)
    except TypeError as e:
        raise InvalidPlan(f"Missing or invalid arguments for {a.name}.") from e
    for key, value in args.items():
        spec = a.schema[key]
        if spec.bounds is not None:
            if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
                raise InvalidPlan(f"{a.name}.{key} must be a finite number.")
            low, high = spec.bounds
            if not low <= value <= high:
                raise InvalidPlan(f"{a.name}.{key} is outside its allowed range.")
        elif value is None and key == "title":
            continue
        elif not isinstance(value, str):
            raise InvalidPlan(f"{a.name}.{key} must be text; output references are not executable yet.")
        else:
            if key not in {'text', 'query', 'label', 'title'} and re.search(r'\{(?:app|path|kind|artist)\}', value):
                raise InvalidPlan('Unresolved target parameter.')
            if not value.strip() and not (key in {"artist", "label", "title"} or
                                        (key == "app" and a.name == "minimise") or
                                        (key == "text" and a.name == "new_note")):
                raise InvalidPlan(f"{a.name}.{key} cannot be empty.")
            if key == "kind" and value not in {"auto", "track", "artist", "album", "playlist"}:
                raise InvalidPlan("Unsupported music kind.")
            if key == "key" and value not in {"play", "pause", "play_pause", "next", "previous", "mute"}:
                raise InvalidPlan("Unsupported media key.")
            if key == "at" and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                raise InvalidPlan("Alarm time must be HH:MM in 24-hour time.")


@dataclass(frozen=True)
class Parameter:
    bounds: tuple[float, float] | None = None


NUMERIC_PARAMETERS = {
    ('set_volume', 'level'): (0, 100),
    ('change_volume', 'step'): (-100, 100),
    ('wait', 'seconds'): (0.1, 5),
    ('set_timer', 'seconds'): (1, 604800),
}


@dataclass
class Action:
    name: str
    fn: Callable[..., Result]
    risk: int
    params: dict[str, str]              # name -> short description
    describe: Callable[..., str]        # used for "Shall I ...?"
    for_brain: bool = False             # may the brain use it in new plans?
    note: str = ""                      # hint for the brain
    schema: dict[str, Parameter] = field(default_factory=dict)

    def __post_init__(self):
        self.schema = {key: Parameter(NUMERIC_PARAMETERS.get((self.name, key))) for key in self.params}


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
    from hands import apps, files, media, notes, timers, web, window_control  # noqa: F401
