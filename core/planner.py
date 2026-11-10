"""Planner: turns an Intent into named-action steps.

Order: saved recipe -> built-in way -> ask the brain to plan with Otto's building blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core import recipes
from core.details import Intent
from hands.registry import ACTIONS, brain_menu


@dataclass
class Plan:
    steps: list[dict]
    source: str                    # builtin / recipe / brain:<model>
    key: str = ""                  # recipe key for "save that"
    params: dict = field(default_factory=dict)
    say_first: str = ""            # e.g. files list
    error: str = ""                # when no plan could be made


def _step(do: str, **kw) -> dict:
    return {"do": do, "with": {k: v for k, v in kw.items() if v is not None}}


def builtin_steps(i: Intent) -> list[dict] | None:
    p = i.params
    a = (i.area, i.action)
    if i.area == "apps":
        app = (p.get("app") or "").strip()
        if a[1] == "open" and app:
            return [_step("open_app", app=app)]
        if a[1] == "switch_to" and app:
            return [_step("switch_to", app=app)]
        if a[1] == "minimise":
            return [_step("minimise", app=app)]
        if a[1] == "close" and app:
            return [_step("close_app", app=app)]
        if a[1] == "click_button" and app and p.get("button"):
            return [_step("click_button", app=app, button=p["button"])]
        if a[1] == "search_in_app" and app and p.get("query"):
            from hands.apps import builtin_search_link
            if builtin_search_link(app, p["query"]):
                return [_step("search_in_app", app=app, query=p["query"])]
            return None  # needs a recipe or a brain plan
    if i.area == "media":
        keys = {"play_pause": "play_pause", "next": "next", "previous": "previous", "mute": "mute"}
        if a[1] in keys:
            return [_step("media_key", key=keys[a[1]])]
        if a[1] == "volume_up":
            return [_step("change_volume", step=abs(int(p.get("step", 10))))]
        if a[1] == "volume_down":
            return [_step("change_volume", step=-abs(int(p.get("step", 10))))]
        if a[1] == "set_volume" and p.get("level") is not None:
            return [_step("set_volume", level=p["level"])]
    if i.area == "web":
        if a[1] == "open_site" and p.get("site"):
            return [_step("open_site", site=p["site"])]
        if a[1] == "web_search" and p.get("query"):
            return [_step("web_search", query=p["query"])]
    if i.area == "files":
        if p.get("path"):
            return [_step("open_path", path=p["path"])]
        if p.get("query"):
            return [_step("find_files", query=p["query"])]
    if i.area == "notes":
        if a[1] == "add_to_note" and p.get("text"):
            return [_step("add_to_note", text=p["text"])]
        if a[1] == "new_note" and ("text" in p or p.get("title")):
            return [_step("new_note", text=p.get("text", ""), title=p.get("title"))]
    if i.area == "timer":
        if a[1] == "set_timer" and p.get("seconds"):
            return [_step("set_timer", seconds=float(p["seconds"]), label=p.get("label", ""))]
        if a[1] == "set_alarm" and p.get("at"):
            return [_step("set_alarm", at=p["at"], label=p.get("label", ""))]
        if a[1] == "time_left":
            return [_step("time_left")]
        if a[1] == "cancel":
            return [_step("cancel_timers")]
    return None


def recipe_key(i: Intent) -> str:
    return recipes.key_for(i.area, i.action, i.params.get("app", ""))


def brain_plan(text: str, i: Intent | None, brain) -> Plan:
    goal = f"The user said: \"{text}\"."
    if i:
        goal += f" Understood as: {i.area} / {i.action} with {i.params}."
    prompt = (f"{goal}\nPlan it as a short list of steps using ONLY these building blocks:\n{brain_menu()}\n"
              "Rules: at most 8 steps; open or switch to the app before using hotkey or type_text; add a "
              "wait of 1-2 seconds after opening an app; prefer app links (like spotify:search:...) or "
              "keyboard shortcuts over clicking.\n"
              "Reply with only JSON: {\"steps\": [{\"do\": \"name\", \"with\": {...}}], \"say\": \"one short sentence for the user\"}. "
              "If it can't be done with these blocks, reply {\"steps\": [], \"say\": \"why not\"}.")
    try:
        r = brain.ask("decide", prompt, want_json=True, required=("steps",))
    except Exception as e:
        return Plan([], "none", error=f"I couldn't reach a brain to work that out ({e}).")
    steps = []
    for s in (r.data.get("steps") or [])[:8]:
        if not isinstance(s, dict):
            continue
        do = s.get("do")
        if do in ACTIONS and ACTIONS[do].for_brain:
            args = s.get("with") or {}
            allowed = set(ACTIONS[do].params)
            steps.append({"do": do, "with": {k: v for k, v in args.items() if k in allowed}})
        else:
            return Plan([], "none", error=f"The plan used a step I don't allow ({do}), so I didn't run it.")
    if not steps:
        return Plan([], "none", error=r.data.get("say") or "I don't know how to do that yet.")
    return Plan(steps, f"brain:{r.model}", key=recipe_key(i) if i else "", params=i.params if i else {})


def make_plan(i: Intent, text: str, brain) -> Plan:
    key = recipe_key(i)
    saved = recipes.get(key)
    if saved:
        return Plan(recipes.fill(saved["steps"], i.params), "recipe", key, i.params)
    steps = builtin_steps(i)
    if steps:
        return Plan(steps, "builtin", key, i.params)
    return brain_plan(text, i, brain)
