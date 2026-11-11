"""Small Windows helpers: windows, focus, keyboard. Everything else in hands/ builds on these.

Imports of Windows-only libraries happen inside functions, so the rest of Otto can still be
loaded (and tested in --dry-run) on other systems.
"""

from __future__ import annotations

import ctypes
import os
import time

IS_WINDOWS = os.name == "nt"
OTTO_WINDOWS: set[int] = set()  # Otto's own terminal window(s), recorded at start-up

VK = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2,
      "mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF}


def press_vk(code: int, times: int = 1) -> None:
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(code, 0, 0, 0)
        user32.keybd_event(code, 0, 2, 0)  # KEYEVENTF_KEYUP
        time.sleep(0.02)


def foreground() -> int:
    return ctypes.windll.user32.GetForegroundWindow() if IS_WINDOWS else 0


def remember_otto_window() -> None:
    if IS_WINDOWS:
        OTTO_WINDOWS.add(foreground())
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            OTTO_WINDOWS.add(console)


def window_info(hwnd: int) -> dict:
    import psutil
    import win32gui
    import win32process

    title = win32gui.GetWindowText(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = psutil.Process(pid).name()
    except Exception:
        pid, exe = 0, ""
    return {"hwnd": hwnd, "title": title, "pid": pid, "exe": exe,
            "rect": win32gui.GetWindowRect(hwnd)}


def windows() -> list[dict]:
    """Visible top-level windows with a title (not Otto's own)."""
    import win32gui

    found = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) and hwnd not in OTTO_WINDOWS:
            found.append(hwnd)
        return True

    win32gui.EnumWindows(cb, None)
    return [window_info(h) for h in found]


def find_window(app_name: str) -> dict | None:
    """The window that best matches an app name, by its program name or title."""
    from rapidfuzz import fuzz

    name = app_name.lower()
    best, best_score = None, 0
    for w in windows():
        exe = w["exe"].lower().removesuffix(".exe")
        title = w["title"].lower()
        score = max(fuzz.ratio(name, exe), fuzz.partial_ratio(name, title) if len(name) > 3 else 0,
                    100 if name in title.split(" - ")[-1] else 0)
        if score > best_score:
            best, best_score = w, score
    return best if best_score >= 80 else None


def focus(hwnd: int) -> bool:
    from core.action_runtime import check
    check()
    from pywinauto import Desktop

    try:
        w = Desktop(backend="win32").window(handle=hwnd)
        if w.is_minimized():
            w.restore()
        w.set_focus()
        return True
    except Exception:
        return False


def minimise(hwnd: int) -> None:
    import win32gui
    win32gui.ShowWindow(hwnd, 6)  # SW_MINIMIZE


def close(hwnd: int) -> None:
    import win32gui
    win32gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE: the app can still ask "save changes?"


_SPECIAL = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+"}
_KEYS = {"enter": "{ENTER}", "return": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}", "escape": "{ESC}",
         "space": "{SPACE}", "backspace": "{BACKSPACE}", "delete": "{DELETE}", "up": "{UP}",
         "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}", "home": "{HOME}", "end": "{END}",
         "win": "{VK_LWIN}", "f5": "{F5}", "f11": "{F11}"}


def hotkey(keys: str) -> None:
    """'ctrl+l', 'ctrl+shift+t', 'enter'."""
    from core.action_runtime import check
    check()
    from pywinauto.keyboard import send_keys

    parts = [p.strip().lower() for p in keys.replace(" ", "").split("+") if p.strip()]
    mods = "".join(_SPECIAL[p] for p in parts[:-1] if p in _SPECIAL)
    last = parts[-1]
    key = _KEYS.get(last, last if len(last) == 1 else "{" + last.upper() + "}")
    send_keys(mods + key, pause=0.02)


def type_text(text: str) -> None:
    from core.action_runtime import check
    check()
    from pywinauto.keyboard import send_keys

    escaped = "".join("{" + c + "}" if c in "{}+^%~()[]" else c for c in text)
    escaped = escaped.replace("\n", "{ENTER}")
    send_keys(escaped, with_spaces=True, with_newlines=True, pause=0.005)


def focused_is_password() -> bool:
    try:
        from pywinauto.uia_defines import IUIA
        return bool(IUIA().get_focused_element().CurrentIsPassword)
    except Exception:
        return False
