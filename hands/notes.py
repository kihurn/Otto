"""Notes: Otto writes a text file in otto-data/notes and opens it in Notepad.
(Writing the file is more reliable than typing into Notepad, and you keep a copy.)"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime

from core.config import NOTES
from hands.registry import UNDOABLE, Result, action

_last: dict = {}


def _name(text: str, title: str | None) -> str:
    base = title or " ".join(re.findall(r"[A-Za-z0-9]+", text)[:5]) or "note"
    return f"{datetime.now():%Y-%m-%d %H%M} {base[:40]}.txt"


@action("new_note", UNDOABLE, {"text": "what to write", "title": "optional short name"},
        lambda text, title=None: f"write a note: \"{text[:50]}\"")
def new_note(text: str, title: str | None = None) -> Result:
    path = NOTES / _name(text, title)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    _last["path"] = path
    subprocess.Popen(["notepad.exe", str(path)])
    return Result(True, "Written down.", {"path": str(path)})


@action("add_to_note", UNDOABLE, {"text": "what to add"}, lambda text: f"add \"{text[:50]}\" to your last note")
def add_to_note(text: str) -> Result:
    path = _last.get("path")
    if not path:
        notes = sorted(NOTES.glob("*.txt"), key=lambda p: p.stat().st_mtime)
        path = notes[-1] if notes else None
    if not path:
        return new_note(text)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    subprocess.Popen(["notepad.exe", str(path)])
    return Result(True, f"Added to {path.stem[16:] or 'your note'}.")
