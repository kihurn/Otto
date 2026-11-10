"""Teaching examples and the test set.

examples.csv  - what Laya learns from: my starter examples, yours, and brain decisions you confirmed.
test_set.csv  - Laya's exam. Never taught. Decides the confidence zones and whether a newly
                taught Laya is allowed to replace the old one.
"""

from __future__ import annotations

import csv
import threading
from datetime import datetime

from core.config import EXAMPLES_FILE, TEST_FILE

EX_FIELDS = ["text", "area", "action", "source", "added"]
TEST_FIELDS = ["text", "area", "checked"]
_lock = threading.Lock()


def norm(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _read(path, fields) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [{k: (r.get(k) or "").strip() for k in fields} for r in rows if (r.get("text") or "").strip()]


def _write(path, fields, rows) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def load_examples() -> list[dict]:
    return _read(EXAMPLES_FILE, EX_FIELDS)


def load_test() -> list[dict]:
    return _read(TEST_FILE, TEST_FIELDS)


def save_test(rows: list[dict]) -> None:
    with _lock:
        _write(TEST_FILE, TEST_FIELDS, rows)


def test_texts() -> set[str]:
    return {norm(r["text"]) for r in load_test()}


def training_rows(areas: set[str]) -> list[dict]:
    """Examples Laya learns from: newest label wins, test-set requests are never included."""
    exam = test_texts()
    latest: dict[str, str] = {}
    for r in load_examples():
        if r["area"] in areas:
            latest[norm(r["text"])] = r["area"]
    return [{"state": t, "gold": {"area": a}} for t, a in latest.items() if t not in exam]


def add_example(text: str, area: str, action: str = "", source: str = "you") -> bool:
    """Save a teaching example. Returns False (and saves nothing) if it's a test-set request."""
    if not text.strip() or norm(text) in test_texts():
        return False
    with _lock:
        rows = load_examples()
        key = norm(text)
        rows = [r for r in rows if norm(r["text"]) != key]
        rows.append({"text": text.strip(), "area": area, "action": action, "source": source,
                     "added": datetime.now().isoformat(timespec="seconds")})
        _write(EXAMPLES_FILE, EX_FIELDS, rows)
    return True


def remove_example(text: str) -> None:
    with _lock:
        rows = [r for r in load_examples() if norm(r["text"]) != norm(text)]
        _write(EXAMPLES_FILE, EX_FIELDS, rows)
