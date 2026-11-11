"""Finding files with Everything (es.exe), and opening them."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from hands.registry import ASK, READ, UNDOABLE, Result, action

RUNNABLE = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".js", ".jar", ".scr", ".com", ".reg", ".lnk"}
_settings: dict = {}


def configure(settings: dict) -> None:
    _settings.update(settings)


def es_path() -> str | None:
    custom = _settings.get("everything_es_path")
    candidates = [custom] if custom else []
    candidates += [shutil.which("es"), r"C:\Program Files\Everything\es.exe",
                   r"C:\Program Files (x86)\Everything\es.exe",
                   str(Path(__file__).resolve().parent.parent / "tools" / "es.exe")]
    return next((c for c in candidates if c and Path(c).is_file()), None)


_SKIP_PATHS = ("\\appdata\\", "\\site-packages\\", "\\node_modules\\", "\\.venv\\", "\\venv\\", "\\__pycache__\\",
               "\\.git\\", "\\.cache\\", "\\.otto\\", "\\program files", "\\windows\\", "\\$recycle.bin\\",
               "\\.vscode\\", "\\.nuget\\", "\\.cargo\\", "\\.rustup\\", "\\go\\pkg\\", "\\otto-data\\laya\\")
_CODE_EXT = {".py", ".pyc", ".pyd", ".js", ".ts", ".tsx", ".jsx", ".d.ts", ".json", ".map", ".dll", ".lib", ".h",
             ".cpp", ".c", ".rs", ".go", ".java", ".class", ".so", ".pdb", ".lock", ".yml", ".yaml", ".toml", ".cfg"}
_DOC_EXT = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv", ".txt", ".md", ".odt", ".rtf",
            ".png", ".jpg", ".jpeg", ".heic", ".webp", ".mp4", ".mov", ".mkv", ".mp3", ".wav", ".zip"}


def _rank(path: str, words: list[str]) -> float:
    p = Path(path)
    low = path.lower()
    name = p.name.lower()
    score = 0.0
    score += 3 if p.suffix.lower() in _DOC_EXT else 0
    score -= 4 if p.suffix.lower() in _CODE_EXT else 0
    score += 2 * sum(w in name for w in words)                 # words in the file name, not just the folder
    score += 1 if any(f"\\{d}\\" in low for d in ("documents", "desktop", "downloads", "onedrive", "pictures")) else 0
    return score


def search(query: str, limit: int = 8) -> tuple[list[str], str | None]:
    """Search your own folders with Everything, skipping program, system and code folders."""
    es = es_path()
    if not es:
        return [], ("I need Everything's command-line tool (es.exe) to search files. "
                    "See the README, 'Install Everything'.")
    try:
        out = subprocess.run([es, "-n", "300", "-sort", "date-modified-descending", "-path", str(Path.home()),
                              *query.split()],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except subprocess.TimeoutExpired:
        return [], "The file search took too long."
    if out.returncode != 0:
        return [], "Everything isn't running. Start the Everything app, then ask again."
    words = [w.lower() for w in query.split() if not w.startswith("ext:")]
    found = [l.strip() for l in out.stdout.splitlines() if l.strip()]
    found = [f for f in found if not any(s in f.lower() for s in _SKIP_PATHS)]
    found.sort(key=lambda f: -_rank(f, words))                 # stable: newest first among equals
    return found[:limit], None


@action("find_files", READ, {"query": "words from the file name"}, lambda query: f"search your files for \"{query}\"")
def find_files(query: str) -> Result:
    from core.tasks import Outcome, OutcomeStatus, Evidence
    found, err = search(query)
    if err:
        return Result(False, err)
    found = [path for path in found if Path(path).exists()]
    data = {'files': found}
    evidence = [Evidence('files.search_and_existence', target={'query':query}, observed={'count':len(found)})]
    if not found:
        return Outcome(OutcomeStatus.VERIFIED, f"I couldn't find any files matching {query}.", data, evidence)
    lines = "\n".join(f"  {i + 1}. {Path(p).name}   ({Path(p).parent})" for i, p in enumerate(found))
    return Outcome(OutcomeStatus.VERIFIED, f"Here's what I found:\n{lines}\nSay \"open 1\" (or another number) to open one.",
                   data, evidence)


def open_risk(path: str) -> int:
    return ASK if Path(path).suffix.lower() in RUNNABLE else UNDOABLE


@action("open_path", UNDOABLE, {"path": "full path of a file or folder"},
        lambda path: f"open {Path(path).name}" + (" (it's a program, so it will run)"
                                                   if Path(path).suffix.lower() in RUNNABLE else ""))
def open_path(path: str) -> Result:
    if not Path(path).exists():
        return Result(False, f"{Path(path).name} doesn't exist any more.")
    os.startfile(path)
    return Result(True, f"Opening {Path(path).name}.")


_FOLDERS = {"downloads": "Downloads", "download": "Downloads", "documents": "Documents", "document": "Documents",
            "docs": "Documents", "desktop": "Desktop", "pictures": "Pictures", "picture": "Pictures",
            "photos": "Pictures", "music": "Music", "videos": "Videos", "video": "Videos"}


def known_folder(text: str) -> str | None:
    """'open my downloads', 'show me the documents folder' -> the real folder path."""
    import re
    home = Path.home()
    core = re.sub(r"^(?:open|show(?: me)?|go to|take me to|pull up|bring up)\s+", "", text.lower().strip())
    core = re.sub(r"^(?:my|the)\s+", "", core)
    core = re.sub(r"\s+folder$", "", core).strip()
    name = _FOLDERS.get(core) or _FOLDERS.get(core.rstrip("s"))
    if not name:
        return None
    for base in (home / name, home / "OneDrive" / name, home / "OneDrive" / "Documents" / name):
        if base.is_dir():
            return str(base)
    return str(home / name)
