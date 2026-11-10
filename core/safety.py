"""The safety gate. Every action Otto takes goes through run_plan(), which no interface, recipe or
brain reply can skip:

  read      -> just do it
  undoable  -> do it and say so
  ask first -> only runs with confirmed=True (Otto showed you exactly what will happen and you said yes)
"""

from __future__ import annotations

from core import log
from hands.registry import ACTIONS, ASK, RISK_NAMES, Result


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


def run_plan(steps: list[dict], confirmed: bool = False, dry_run: bool = False, why: str = "") -> Result:
    risk = plan_risk(steps)
    if risk >= ASK and not confirmed:
        raise NeedsConfirm(describe(steps))
    said, data, ok = [], {}, True
    for s in steps:
        a = ACTIONS[s["do"]]
        args = s.get("with", {})
        if dry_run:
            if s["do"] != "wait":
                said.append(f"[dry run] would {describe([s])}.")
            continue
        try:
            res = a.fn(**args)
        except TypeError as e:
            res = Result(False, f"That step was set up wrongly ({e}).")
        except Exception as e:
            res = Result(False, f"Something went wrong: {type(e).__name__}: {e}"[:200])
        log.write({"type": "action", "do": s["do"], "with": args, "risk": RISK_NAMES[step_risk(s)],
                   "ok": res.ok, "say": res.say, "why": why})
        data.update(res.data)
        if res.say and res.say != "Done." or not res.ok:
            said.append(res.say)
        if not res.ok:
            ok = False
            break
    text = " ".join(x for x in said if x) or ("Done." if ok else "That didn't work.")
    return Result(ok, text, data)
