"""otto eval: how well does Otto understand real sentences?

Each line of otto-data/eval.csv is something you might say, plus what should happen:
  route       fast (Laya + an exact rule), loop (the Qwen agent loop) or reply (just an answer, no action)
  first_tool  the first tool that should be used (open, media, type, click, ...), "none" for no action
  args        words that must appear in that tool's details, separated by ";"
  live        1 if the sentence is also part of the live check on Windows
  must_ask    1 if Otto must ask you before doing it (buying, sending, deleting, running commands...)

Otto runs in dry-run, so nothing on the PC is touched, but the real Laya and the real Qwen decide.
Only the decision is judged here; the live check on Windows judges what really happens.
"""
from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from core import config

# What the old pipeline's actions are called in the new tool menu, so both cores can be scored alike.
OLD_TO_TOOL = {
    "open_app": "open", "switch_to": "open", "open_path": "open", "open_site": "open", "open_link": "open",
    "search_in_app": "open", "web_search": "open",
    "find_files": "find_files",
    "play_music": "media", "play_liked": "media", "media_key": "media", "now_playing": "media",
    "get_volume": "media", "set_volume": "media", "change_volume": "media",
    "list_audio_outputs": "audio_output", "get_audio_output": "audio_output", "set_audio_output": "audio_output",
    "set_audio_output_id": "audio_output", "undo_audio_output": "audio_output",
    "set_timer": "timer", "set_alarm": "timer", "time_left": "timer", "cancel_timers": "timer",
    "new_note": "note", "add_to_note": "note",
    "close_app": "close", "minimise": "close",
    "click_button": "click", "toggle": "click", "set_field": "type",
    "type_in_app": "type", "type_text": "type", "hotkey": "keys",
    "app_goal": "", "visual_task": "",
}
LOOP_ACTIONS = {"app_goal", "visual_task"}


@dataclass
class EvalCase:
    text: str
    route: str = ""
    first_tool: str = ""
    args: list[str] = field(default_factory=list)
    live: bool = False
    must_ask: bool = False


@dataclass
class Decision:
    route: str                  # fast / loop / reply / error
    tool: str                   # first tool used ("" = none)
    args: dict
    asks: bool                  # did Otto ask before acting (at any point)?
    reply: str = ""


@dataclass
class Report:
    total: int
    right: int
    results: list[dict]
    safety_regressions: list[str]


def load_cases(path: Path | None = None) -> list[EvalCase]:
    path = path or (config.DATA / "eval.csv" if (config.DATA / "eval.csv").exists() else config.DEFAULTS / "eval.csv")
    cases = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            cases.append(EvalCase(
                text, (row.get("route") or "").strip(), (row.get("first_tool") or "").strip(),
                [a.strip() for a in (row.get("args") or "").split(";") if a.strip()],
                (row.get("live") or "").strip() == "1", (row.get("must_ask") or "").strip() == "1"))
    return cases


def _fresh(otto) -> None:
    """Each sentence is judged on its own: no question left open, no follow-up context."""
    if otto.pending and getattr(otto.pending, "task", None):
        otto.pending.task.cancel.set()
    otto.pending = None
    otto.last = None
    otto.rephrase_of = None
    otto.history.clear()
    otto.last_app = None
    otto.last_web_query = None


def decide_only(otto, text: str) -> Decision:
    """What Otto decides for one sentence, in dry-run."""
    _fresh(otto)
    try:
        reply = otto.handle(text)
    except Exception as error:
        return Decision("error", "", {}, False, f"{type(error).__name__}: {error}"[:200])
    trace = otto.trace
    asks = bool(otto.pending and otto.pending.kind in ("confirm_plan", "agent_confirm")) \
        or reply.text.startswith("Just checking")
    agent = trace.get("agent")                  # filled in by the new core (agent loop)
    if agent is not None:
        first = agent.get("first") or {}
        decision = Decision(agent.get("route", "loop"), first.get("tool", ""), first.get("args", {}),
                            asks or bool(agent.get("asked")), reply.text)
        _fresh(otto)
        return decision
    steps = [s for s in (trace.get("plan") or {}).get("steps", []) if s.get("do") != "wait"]
    if not steps and otto.pending is not None and getattr(otto.pending, "plan", None):
        steps = [s for s in otto.pending.plan.steps if s.get("do") != "wait"]
    _fresh(otto)
    if not steps:
        return Decision("reply", "", {}, asks, reply.text)
    route = "loop" if any(s["do"] in LOOP_ACTIONS for s in steps) else "fast"
    first = steps[0]
    return Decision(route, OLD_TO_TOOL.get(first["do"], first["do"]), dict(first.get("with", {})), asks, reply.text)


def judge(case: EvalCase, d: Decision) -> tuple[bool, str]:
    """(right?, why not)."""
    why = []
    if d.route == "error":
        return False, d.reply
    if case.route and d.route != case.route:
        why.append(f"route {d.route}, expected {case.route}")
    if case.first_tool:
        want = "" if case.first_tool == "none" else case.first_tool
        if d.tool != want:
            why.append(f"tool {d.tool or 'none'}, expected {case.first_tool}")
    details = " ".join(str(v) for v in d.args.values()).casefold()
    missing = [a for a in case.args if a.casefold() not in details]
    if missing:
        why.append(f"missing {', '.join(missing)}")
    if case.must_ask and not d.asks:
        why.append("did not ask first")
    return not why, "; ".join(why)


def score(cases: list[EvalCase], decide: Callable[[str], Decision]) -> Report:
    results, right, regressions = [], 0, []
    for case in cases:
        t0 = time.perf_counter()
        d = decide(case.text)
        ok, why = judge(case, d)
        right += ok
        if case.must_ask and not d.asks:
            regressions.append(case.text)
        results.append({"text": case.text, "ok": ok, "why": why, "ms": round((time.perf_counter() - t0) * 1000),
                        "decision": asdict(d)})
    return Report(len(cases), right, results, regressions)


def save_run(report: Report, core: str) -> Path:
    folder = config.DATA / "eval_runs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y-%m-%d-%H%M%S')}-{core}.json"
    path.write_text(json.dumps({"core": core, **asdict(report)}, indent=1, ensure_ascii=False), encoding="utf-8")
    return path
