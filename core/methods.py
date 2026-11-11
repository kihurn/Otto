"""Methods Otto has learned for doing something inside an app: a short list of named buttons to press.

A method is saved only when the user says "save that" after a multi-step success. Next time the same goal
comes up in the same app, the steps are replayed by button name with no model call. If a saved step can no
longer be found the method gets a miss; two misses retire it and Otto goes back to working it out.

The idea (save on the user's say-so, replay by control name, retire after two misses) follows Nus
Companion's walkthroughs (companion/src/guide/walkthroughs.js, MIT licence); see THIRD_PARTY_NOTICES.md.
"""
from __future__ import annotations

import re
from datetime import datetime

from core.config import DATA, load_json, save_json

METHODS_FILE = DATA / "methods.json"
MAX_METHODS = 200


def key_for(app: str, goal: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (goal or "").lower()).strip("-")[:60]
    return f"{(app or '').lower().strip()}::{slug}"


def find(app: str, goal: str) -> list[str] | None:
    """The saved button names for this app and goal, or None."""
    entry = load_json(METHODS_FILE, {}).get(key_for(app, goal))
    if not entry or entry.get("stale") or not entry.get("steps"):
        return None
    return list(entry["steps"])


def save(app: str, goal: str, steps: list[str]) -> bool:
    steps = [str(s) for s in steps if s]
    if not app or not goal or not steps:
        return False
    data = load_json(METHODS_FILE, {})
    if len(data) >= MAX_METHODS and key_for(app, goal) not in data:
        oldest = min(data, key=lambda k: data[k].get("last_ok", ""))
        data.pop(oldest)
    now = datetime.now().isoformat(timespec="seconds")
    data[key_for(app, goal)] = {"app": app, "goal": goal, "steps": steps, "runs": 0, "misses": 0,
                                "stale": False, "created": now, "last_ok": now}
    save_json(METHODS_FILE, data)
    return True


def record(app: str, goal: str, worked: bool) -> None:
    """Count a replay. Two misses retire the method."""
    data = load_json(METHODS_FILE, {})
    entry = data.get(key_for(app, goal))
    if not entry:
        return
    if worked:
        entry["runs"] = entry.get("runs", 0) + 1
        entry["misses"] = 0
        entry["last_ok"] = datetime.now().isoformat(timespec="seconds")
    else:
        entry["misses"] = entry.get("misses", 0) + 1
        entry["stale"] = entry["misses"] >= 2
    save_json(METHODS_FILE, data)
