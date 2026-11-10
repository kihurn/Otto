"""Recipes: saved ways of doing a task, replayed without asking any model.

Key = area.action.target, e.g. "apps.search_in_app.discord". Steps use {placeholders} filled from
the request, e.g. {"do": "type_text", "with": {"text": "{query}"}}.
"""

from __future__ import annotations

import copy
from datetime import datetime

from core.config import RECIPES_FILE, load_json, save_json


def _all() -> dict:
    return load_json(RECIPES_FILE, {})


def key_for(area: str, action: str, target: str = "") -> str:
    return f"{area}.{action}.{(target or '').lower().strip()}".rstrip(".")


def get(key: str) -> dict | None:
    r = _all().get(key)
    if not r:
        return None
    if r.get("used", 0) >= 3 and r.get("worked", 0) / max(1, r["used"]) < 0.6:
        return None  # it keeps failing (an app update?), so stop trusting it
    return r


def fill(steps: list[dict], params: dict) -> list[dict]:
    out = copy.deepcopy(steps)
    for s in out:
        for k, v in list(s.get("with", {}).items()):
            if isinstance(v, str):
                for pk, pv in params.items():
                    v = v.replace("{" + pk + "}", str(pv))
                s["with"][k] = v
    return out


def templatise(steps: list[dict], params: dict) -> list[dict]:
    """Turn concrete steps back into a template: 'lofi' -> '{query}' wherever it appears."""
    out = copy.deepcopy(steps)
    for s in out:
        for k, v in list(s.get("with", {}).items()):
            if isinstance(v, str):
                for pk, pv in params.items():
                    if isinstance(pv, str) and pv and pk != "app":
                        v = v.replace(pv, "{" + pk + "}")
                s["with"][k] = v
    return out


def save(key: str, steps: list[dict], params: dict, learned_from: str, example: str) -> None:
    data = _all()
    data[key] = {"steps": templatise(steps, params), "learned_from": learned_from, "example": example,
                 "created": datetime.now().isoformat(timespec="seconds"), "used": 0, "worked": 0}
    save_json(RECIPES_FILE, data)


def forget(key: str) -> bool:
    data = _all()
    if key in data:
        data.pop(key)
        save_json(RECIPES_FILE, data)
        return True
    return False


def record(key: str, ok: bool) -> None:
    data = _all()
    if key in data:
        data[key]["used"] = data[key].get("used", 0) + 1
        data[key]["worked"] = data[key].get("worked", 0) + int(ok)
        save_json(RECIPES_FILE, data)
