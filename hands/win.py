"""Small Windows helpers: windows, focus, keyboard. Everything else in hands/ builds on these.

Imports of Windows-only libraries happen inside functions, so the rest of Otto can still be
loaded (and tested in --dry-run) on other systems.
"""

from __future__ import annotations

import re
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

    name = ' '.join(app_name.casefold().split())
    if not name:
        return None
    # Office's process name differs from its spoken name. A workspace or document title
    # mentioning Word is not proof of app ownership, even with a high fuzzy score.
    if name in {'word', 'microsoft word', 'winword'}:
        return next((w for w in windows() if w['exe'].casefold() == 'winword.exe'), None)
    best, best_score = None, 0
    for w in windows():
        exe = w["exe"].lower().removesuffix(".exe")
        title = w["title"].lower()
        # Apps put their own name at the END of the title ("Document1 - Word"). Only that part is compared:
        # matching anywhere in the title made a Notepad file called "... in word ..." count as Word.
        app_part = title.split(" - ")[-1]
        # "Google Chrome" runs as chrome.exe, and with a Chrome profile its title ends in the profile's name
        # ("Banana - Google Search - Google Chrome - Ki"), so also accept the name's last word being the program.
        # Also a program named for more than the app ("Terminal" runs as WindowsTerminal.exe, titled "Windows PowerShell").
        squashed = name.replace(" ", "")
        last_word = 95 if len(exe) >= 5 and (name.split()[-1] == exe or (len(squashed) >= 5 and exe.endswith(squashed))) else 0
        score = max(fuzz.ratio(name, exe), fuzz.partial_ratio(name, app_part) if len(name) > 3 else 0,
                    100 if name in app_part else 0, last_word)
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


MODIFIERS = ("ctrl", "alt", "shift")          # the order every shortcut is written in after parse_hotkey
_KEY_NAMES = {"enter", "return", "tab", "esc", "escape", "space", "backspace", "delete", "del", "insert", "home",
              "end", "pageup", "pagedown", "up", "down", "left", "right", "win", *(f"f{n}" for n in range(1, 13))}


def parse_hotkey(keys: str) -> tuple[tuple[str, ...], str]:
    """'Shift + Ctrl + Enter' -> (("ctrl", "shift"), "enter"). Only ctrl/alt/shift may come before the last key and
    the last key must be one real key, otherwise ValueError. The safety gate and hotkey() both use this, so what
    is checked is exactly what is pressed (Codex review 19 Nov: "a+enter" was checked as harmless, then the "a"
    was silently dropped and a plain Enter was pressed)."""
    parts = [p for p in str(keys).lower().replace(" ", "").split("+") if p]
    if not parts:
        raise ValueError("no keys")
    *mods, last = ["ctrl" if p == "control" else p for p in parts]
    if any(m not in MODIFIERS for m in mods) or len(set(mods)) != len(mods):
        raise ValueError(f"only ctrl, alt and shift can come before the last key: {keys!r}")
    if last in MODIFIERS or not (last in _KEY_NAMES or re.fullmatch(r"[a-z0-9]", last)):
        raise ValueError(f"not a key: {last!r}")
    last = {"return": "enter", "escape": "esc", "del": "delete"}.get(last, last)
    return tuple(m for m in MODIFIERS if m in mods), last


def hotkey(keys: str) -> None:
    """'ctrl+l', 'ctrl+shift+t', 'enter'. Refuses anything parse_hotkey can't read in full."""
    mods, last = parse_hotkey(keys)
    from core.action_runtime import check
    check()
    from pywinauto.keyboard import send_keys

    key = _KEYS.get(last, last if len(last) == 1 else "{" + last.upper() + "}")
    send_keys("".join(_SPECIAL[m] for m in mods) + key, pause=0.02)


def type_text(text: str) -> None:
    from core.action_runtime import check
    check()
    from pywinauto.keyboard import send_keys

    escaped = "".join("{" + c + "}" if c in "{}+^%~()[]" else c for c in text)
    escaped = escaped.replace("\n", "{ENTER}")
    send_keys(escaped, with_spaces=True, with_newlines=True, pause=0.005)


def focused_is_password() -> bool | None:
    """True / False, or None when Windows couldn't tell. Typing treats None as "maybe a password" and refuses
    (Codex review 19 Nov: a failed check used to count as "not a password")."""
    try:
        from pywinauto.uia_defines import IUIA
        return bool(IUIA().get_focused_element().CurrentIsPassword)
    except Exception:
        return None


def window_at(x: int, y: int) -> int:
    """The top-level window that is really on top at this screen point (0 if Windows can't say)."""
    try:
        import win32gui
        hwnd = win32gui.WindowFromPoint((int(x), int(y)))
        return win32gui.GetAncestor(hwnd, 2) if hwnd else 0     # GA_ROOT: the whole window, not a part of it
    except Exception:
        return 0


def exists(hwnd: int) -> bool:
    try:
        import win32gui
        return bool(win32gui.IsWindow(hwnd)) and bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False


def is_minimised(hwnd: int) -> bool:
    import win32gui
    return bool(win32gui.IsIconic(hwnd))


def idle_seconds() -> float | None:
    """Seconds since the last key press or mouse move anywhere (Windows' GetLastInputInfo); None if unknown."""
    if not IS_WINDOWS:
        return None

    class LastInput(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LastInput(ctypes.sizeof(LastInput), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


PAUSE = 1.0           # seconds without typing before Otto borrows the screen
PAUSE_WAIT = 5.0      # ...but never waits longer than this (the user's own Enter to Otto also counts as typing)
NEW_WINDOW_WAIT = 4.0


def wait_for_pause() -> None:
    end = time.monotonic() + PAUSE_WAIT
    while time.monotonic() < end:
        idle = idle_seconds()
        if idle is None or idle >= PAUSE:
            return
        time.sleep(0.2)


class _Borrowed:
    def __init__(self):
        self.new: list[int] = []       # the windows Otto opened (and minimised)


def _new_windows(exe: str, before: set[int]) -> list[int]:
    return [w["hwnd"] for w in windows() if w["hwnd"] not in before and w["exe"].casefold() == exe]


class screen_borrowed:
    """Background mode (step 4c): `with screen_borrowed("chrome.exe") as b:` opens something without keeping the
    screen. Waits for a pause in typing; afterwards only windows of `exe` that appeared inside the block are
    minimised (b.new), and the user's window comes back only if one of those is in front (if the user has moved
    on, they are left alone). The new windows are minimised even when the block fails or is cancelled (Windows then
    usually brings your window back by itself; a cancel can stop Otto putting it back)."""

    def __init__(self, exe: str):
        self.exe, self.b = exe.casefold(), _Borrowed()

    def __enter__(self) -> _Borrowed:
        if IS_WINDOWS:
            wait_for_pause()
            self.mine, self.before = foreground(), {w["hwnd"] for w in windows()}
        return self.b

    def __exit__(self, kind, error, trace) -> None:
        if not IS_WINDOWS:
            return
        end = time.monotonic() + (0 if kind else NEW_WINDOW_WAIT)
        while True:
            self.b.new = _new_windows(self.exe, self.before)
            if self.b.new or time.monotonic() >= end:
                break
            time.sleep(0.2)
        front = foreground()
        for hwnd in self.b.new:
            minimise(hwnd)
        if front in self.b.new and self.mine and exists(self.mine):
            try:
                focus(self.mine)
            except BaseException:          # a cancel while putting the window back is fine: nothing else to do
                pass
