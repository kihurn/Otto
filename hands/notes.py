"""Notes: Otto writes a text file in otto-data/notes and opens it in Notepad.
(Writing the file is more reliable than typing into Notepad, and you keep a copy.)"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime

from core.config import NOTES
from hands.registry import UNDOABLE, Result, action
from core.action_runtime import check
from core.tasks import Evidence, Outcome, OutcomeStatus

_last: dict = {}


def _name(text: str, title: str | None) -> str:
    base = title or " ".join(re.findall(r"[A-Za-z0-9]+", text)[:5]) or "note"
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base).strip(' .') or 'note'
    return f"{datetime.now():%Y-%m-%d %H%M} {base[:40]}.txt"


@action("new_note", UNDOABLE, {"text": "what to write", "title": "optional short name"},
        lambda text, title=None: f"write a note: \"{text[:50]}\"")
def new_note(text: str, title: str | None = None) -> Result:
    original = NOTES / _name(text, title)
    content = text.strip() + '\n'
    for index in range(100):
        path = original if not index else original.with_stem(f'{original.stem} {index+1}')
        check()
        try:
            with path.open('x', encoding='utf-8') as handle:
                handle.write(content)
            break
        except FileExistsError:
            continue
    else:
        return Result(False, 'I could not reserve a unique note name.')
    _last["path"] = path
    return _confirm_note(path, content, 'Written down.')


def _confirm_note(path, expected, say):
    if path.read_text(encoding='utf-8') != expected:
        return Outcome(OutcomeStatus.UNCERTAIN, 'The note contents did not match.', side_effect_possible=True)
    check()
    try:
        subprocess.Popen(['notepad.exe', str(path)])
    except OSError:
        pass
    return Outcome(OutcomeStatus.VERIFIED, say, {'path':str(path)},
                   [Evidence('notes.file_readback', observed={'path':str(path), 'characters':len(expected)})])


@action("add_to_note", UNDOABLE, {"text": "what to add"}, lambda text: f"add \"{text[:50]}\" to your last note")
def add_to_note(text: str) -> Result:
    path = _last.get("path")
    if not path:
        notes = sorted(NOTES.glob("*.txt"), key=lambda p: p.stat().st_mtime)
        path = notes[-1] if notes else None
    if not path:
        return new_note(text)
    if not path.resolve().is_relative_to(NOTES.resolve()):
        return Result(False, 'That note is outside the notes folder.')
    before = path.read_text(encoding='utf-8')
    addition = text.strip() + '\n'
    check()
    with path.open('a', encoding='utf-8') as f:
        f.write(addition)
    return _confirm_note(path, before + addition, f"Added to {path.stem[16:] or 'your note'}.")
