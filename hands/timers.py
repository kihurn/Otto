"""Timers, alarms and reminders. They run while Otto is open, and announce themselves with a
Windows notification, a sound, and Otto's voice when voice replies are on."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from hands.registry import READ, UNDOABLE, Result, action

_timers: dict[int, dict] = {}
_next_id = [1]
announce = [print]  # replaced by Otto with something that also speaks


def human(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' * (h != 1)}")
    if m:
        parts.append(f"{m} minute{'s' * (m != 1)}")
    if s and not h:
        parts.append(f"{s} second{'s' * (s != 1)}")
    return " and ".join(parts) or "0 seconds"


def _notify(title: str, message: str) -> None:
    try:
        from winotify import Notification, audio
        n = Notification(app_id="Otto", title=title, msg=message, duration="long")
        n.set_audio(audio.LoopingAlarm, loop=False)
        n.show()
    except Exception:
        try:
            import winsound
            winsound.MessageBeep()
        except Exception:
            pass


def _fire(tid: int) -> None:
    t = _timers.pop(tid, None)
    if not t:
        return
    msg = (f"Reminder: {t['label']}" if t["kind"] == "reminder" else
           f"Your {t['length']} timer is done" + (f" ({t['label']})" if t["label"] else "") + ".")
    _notify("Otto", msg)
    announce[0](msg)


def _start(seconds: float, kind: str, label: str, length: str) -> dict:
    tid = _next_id[0]
    _next_id[0] += 1
    th = threading.Timer(seconds, _fire, args=(tid,))
    th.daemon = True
    t = {"id": tid, "ends": time.time() + seconds, "kind": kind, "label": label, "length": length, "thread": th}
    _timers[tid] = t
    th.start()
    return t


@action("set_timer", UNDOABLE, {"seconds": "length in seconds", "label": "optional, what it's for"},
        lambda seconds, label="": f"set a {human(float(seconds))} timer" + (f" for {label}" if label else ""))
def set_timer(seconds, label: str = "") -> Result:
    seconds = float(seconds)
    if seconds <= 0 or seconds > 7 * 86400:
        return Result(False, "That timer length doesn't look right.")
    kind = "reminder" if label else "timer"
    _start(seconds, kind, label, human(seconds))
    if label:
        return Result(True, f"I'll remind you to {label} in {human(seconds)}.")
    return Result(True, f"Timer set for {human(seconds)}.")


@action("set_alarm", UNDOABLE, {"at": "time as HH:MM (24-hour)", "label": "optional"},
        lambda at, label="": f"set an alarm for {at}" + (f" to {label}" if label else ""))
def set_alarm(at: str, label: str = "") -> Result:
    now = datetime.now()
    hh, mm = (int(x) for x in at.split(":")[:2])
    when = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)
    seconds = (when - now).total_seconds()
    _start(seconds, "reminder" if label else "alarm", label or f"it's {when:%H:%M}", human(seconds))
    day = "tomorrow" if when.date() > now.date() else "today"
    return Result(True, f"Alarm set for {when:%I:%M %p} {day}".replace(" 0", " ") + (f", to {label}." if label else "."))


@action("time_left", READ, {}, lambda: "check your timers")
def time_left() -> Result:
    if not _timers:
        return Result(True, "You don't have any timers running.")
    lines = []
    for t in sorted(_timers.values(), key=lambda t: t["ends"]):
        left = human(max(0, t["ends"] - time.time()))
        lines.append(f"{t['label'] or t['length'] + ' timer'}: {left} left")
    return Result(True, "; ".join(lines) + ".")


@action("cancel_timers", UNDOABLE, {}, lambda: "cancel your timers")
def cancel_timers() -> Result:
    n = len(_timers)
    for t in list(_timers.values()):
        t["thread"].cancel()
    _timers.clear()
    return Result(True, "Cancelled your timer." if n == 1 else f"Cancelled {n} timers." if n else
                  "There weren't any timers to cancel.")
