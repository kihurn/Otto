"""Eyes: which window you're using, a screenshot of it, and the clipboard.

A background watcher remembers the last window you used that isn't Otto's own terminal, so
"what's on my screen?" means the thing you were looking at, not Otto.
"""

from __future__ import annotations

import base64
import io
import threading
import time

from hands import win

_last: dict = {}


def _watch() -> None:
    while True:
        try:
            h = win.foreground()
            if h and h not in win.OTTO_WINDOWS:
                info = win.window_info(h)
                if info["title"]:
                    _last.update(info)
        except Exception:
            pass
        time.sleep(0.4)


def start() -> None:
    if win.IS_WINDOWS:
        threading.Thread(target=_watch, daemon=True).start()


def last_other_window() -> dict | None:
    return dict(_last) if _last else None


def screenshot(max_width: int = 1280) -> tuple[str, dict | None]:
    """JPEG of the window you were using (or the whole main screen), as base64."""
    import mss
    from PIL import Image

    target = last_other_window()
    was_typing_to_otto = win.foreground() in win.OTTO_WINDOWS
    region = None
    if target:
        try:
            if win.foreground() != target["hwnd"]:
                win.focus(target["hwnd"])
                time.sleep(0.35)
            l, t, r, b = win.window_info(target["hwnd"])["rect"]
            if r - l > 100 and b - t > 100:
                region = {"left": l, "top": t, "width": r - l, "height": b - t}
        except Exception:
            region = None
    with mss.mss() as s:
        shot = s.grab(region or s.monitors[1])
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    if img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    # hand the keyboard back to Otto's window, but only if you were typing to it
    if was_typing_to_otto:
        for h in win.OTTO_WINDOWS:
            if win.focus(h):
                break
    return base64.b64encode(buf.getvalue()).decode(), target


def capture(hwnd: int | None = None, max_width: int = 1280) -> tuple[str, tuple[int, int, int, int], float]:
    """JPEG (base64) of a window, or the main screen, for the agent's look tool.
    Also returns the captured screen rectangle (left, top, right, bottom) and the scale the image was
    shrunk by, so a position the model gives on the image can be turned back into a screen position.
    Screen positions are physical pixels (mss and GetWindowRect agree when Otto is DPI-aware)."""
    import mss
    from PIL import Image

    with mss.mss() as s:
        region = s.monitors[1]
        if hwnd:
            try:
                l, t, r, b = win.window_info(hwnd)["rect"]
                if r - l > 100 and b - t > 100:
                    region = {"left": l, "top": t, "width": r - l, "height": b - t}
            except Exception:
                pass
        shot = s.grab(region)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    scale = 1.0
    if img.width > max_width:
        scale = max_width / img.width
        img = img.resize((max_width, int(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    rect = (region["left"], region["top"], region["left"] + region["width"], region["top"] + region["height"])
    return base64.b64encode(buf.getvalue()).decode(), rect, scale


def clipboard() -> str:
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(13):  # CF_UNICODETEXT
                return win32clipboard.GetClipboardData(13) or ""
            return ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return ""
