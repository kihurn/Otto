"""Worked examples for the agent: requests that went well, with the tool calls that did them.

When you say "save that" after the agent did something, the request and its calls are stored here
(otto-data/agent_examples.jsonl). Next time, the most similar saved requests are shown to Qwen as examples,
which is how Otto learns your way of asking without retraining the model. The same file can later be used to
fine-tune Qwen.
"""
from __future__ import annotations

import json
import re

from core import config

STOP = {"a", "an", "the", "to", "of", "and", "in", "on", "for", "my", "me", "can", "could", "you", "please", "it",
        "is", "i", "with", "at", "this", "that", "would", "will", "otto", "hey", "up", "some"}


def _file():
    return config.DATA / "agent_examples.jsonl"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.casefold()) if w not in STOP}


def save(request: str, calls: list[dict]) -> bool:
    """Store a verified run. Only the tool names and arguments are kept."""
    kept = [{"tool": c["tool"], "args": c.get("args", {})} for c in calls if c.get("tool")]
    if not request.strip() or not kept:
        return False
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"request": request.strip(), "calls": kept}, ensure_ascii=False) + "\n")
    return True


def load() -> list[dict]:
    path = _file()
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("request") and isinstance(item.get("calls"), list):
            out.append(item)
    return out


def similar(request: str, k: int = 5) -> list[dict]:
    """The k saved examples sharing the most words with this request (newest wins a tie)."""
    want = _words(request)
    if not want:
        return []
    scored = []
    for index, item in enumerate(load()):
        have = _words(item["request"])
        overlap = len(want & have) / len(want | have) if have else 0.0
        if overlap > 0:
            scored.append((overlap, index, item))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [item for _, _, item in scored[:k]]


def as_prompt(items: list[dict]) -> str:
    lines = []
    for item in items:
        calls = "; ".join(f"{c['tool']}({', '.join(f'{k}={v!r}' for k, v in c['args'].items())})" for c in item["calls"])
        lines.append(f'- "{item["request"]}" -> {calls}')
    return "\n".join(lines)
