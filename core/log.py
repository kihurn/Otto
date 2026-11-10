"""One line per request in otto-data/logs/YYYY-MM-DD.jsonl. Never contains keys."""

from __future__ import annotations

import json
import threading
from datetime import datetime

from core.config import LOGS

_lock = threading.Lock()


def write(event: dict) -> None:
    event = {"time": datetime.now().isoformat(timespec="seconds"), **event}
    path = LOGS / f"{datetime.now():%Y-%m-%d}.jsonl"
    line = json.dumps(event, ensure_ascii=False, default=str)
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
