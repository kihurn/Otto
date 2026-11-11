"""The safety gate. Every action Otto takes goes through run_plan(), which no interface, recipe or
brain reply can skip:

  read      -> just do it
  undoable  -> do it and say so
  ask first -> only runs with confirmed=True (Otto showed you exactly what will happen and you said yes)
"""

from __future__ import annotations

from hands.registry import ACTIONS, ASK, Result


class NeedsConfirm(Exception):
    pass


def step_risk(step: dict) -> int:
    a = ACTIONS[step["do"]]
    risk = a.risk
    args = step.get("with", {})
    if step["do"] == "open_path":
        from hands.files import open_risk
        risk = max(risk, open_risk(args.get("path", "")))
    if step["do"] in ("click_button", "type_text", "hotkey"):
        from hands.apps import RISKY_WORDS
        text = " ".join(str(v) for v in args.values())
        if RISKY_WORDS.search(text):
            risk = ASK
    return risk


def plan_risk(steps: list[dict]) -> int:
    return max((step_risk(s) for s in steps), default=0)


def describe(steps: list[dict]) -> str:
    parts = []
    for s in steps:
        a = ACTIONS[s["do"]]
        if s["do"] == "wait":
            continue
        try:
            parts.append(a.describe(**s.get("with", {})))
        except TypeError:
            parts.append(s["do"].replace("_", " "))
    return ", then ".join(parts)


def run_plan(steps: list[dict], confirmed: bool = False, dry_run: bool = False, why: str = "", task=None, progress=lambda message: None, evaluation_backend=None) -> Result:
    # Validate every step before risk checks or any effect, including legacy recipes.
    from core.planner import validate_steps
    from hands.registry import InvalidPlan
    try:
        steps = validate_steps(steps)
    except InvalidPlan as e:
        return Result(False, f"I didn't run that plan: {e}", {"error_code": "invalid_plan"})
    risk = plan_risk(steps)
    if risk >= ASK and not confirmed:
        raise NeedsConfirm(describe(steps))
    from core import executor
    return executor.run(steps, dry_run=dry_run, why=why, task=task, progress=progress,
                        evaluation_backend=evaluation_backend)
