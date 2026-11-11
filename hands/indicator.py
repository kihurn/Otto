"""A visible sign that Otto is operating an app: a thin glow around that window and a small Otto pointer
that glides to each control Otto is about to use. Both disappear when the task ends.

It is drawing only. Mouse clicks pass straight through it, it never takes the keyboard, it is hidden from
screenshots (so Qwen never sees it), and the real Windows mouse cursor is left alone. If anything about it
fails, Otto carries on without it.

Known limit: on a display scaled above 100% the glow can sit slightly off the window's edge.
"""
from __future__ import annotations

import queue
import threading
import time

GLOW = ((11, 94, 82), (25, 168, 144), (46, 230, 197))    # outer to inner: Otto's teal (red, green, blue)
KEY = (1, 2, 3)                                         # the colour Windows treats as see-through
HIDE_FROM_CAPTURE = True                                # only ever switched off by a test that photographs it
_commands: queue.Queue | None = None
_lock = threading.Lock()


def _enabled() -> bool:
    """Only for real, live requests on Windows (never in tests or dry runs), and only if switched on."""
    try:
        from core.action_runtime import current
        from core.config import load_settings
        from hands import win
        state = current.get()
        return bool(win.IS_WINDOWS and state and state[0].mode == 'live'
                    and load_settings().get('app_control', {}).get('indicator', True))
    except Exception:
        return False


def _send(command: tuple) -> None:
    global _commands
    try:
        with _lock:
            if _commands is None:
                _commands = queue.Queue()
                threading.Thread(target=_run, args=(_commands,), daemon=True, name='otto-indicator').start()
        _commands.put(command)
    except Exception:
        pass


def show(hwnd: int) -> None:
    """Glow around this window until hide() (or 30 quiet seconds)."""
    if _enabled():
        _send(('show', hwnd))


def point(rect) -> None:
    """Glide the Otto pointer to the middle of a control (left, top, right, bottom)."""
    if _enabled() and rect:
        _send(('point', ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)))
        time.sleep(0.25)                      # long enough to see where Otto is about to act


def hide() -> None:
    if _commands is not None:
        _send(('hide',))


def _run(commands: queue.Queue) -> None:
    """The overlay's own thread: one plain Windows window covering the screen, see-through except for the
    glow and pointer. (A plain window is used because a Tk window grabs the keyboard when shown.)"""
    try:
        import ctypes
        import win32api
        import win32con
        import win32gui
        from hands import win

        user32 = ctypes.windll.user32
        left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)          # all monitors together
        width, height = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        state = {'target': None, 'want': None, 'at': None, 'seen': time.monotonic(), 'visible': False, 'drawn': None}
        key = win32api.RGB(*KEY)

        def paint(hwnd):
            hdc, ps = win32gui.BeginPaint(hwnd)
            try:
                background = win32gui.CreateSolidBrush(key)
                win32gui.FillRect(hdc, (0, 0, width, height), background)
                win32gui.DeleteObject(background)
                frame = state['drawn']
                if frame:
                    hollow = win32gui.GetStockObject(5)                               # draw outlines only
                    win32gui.SelectObject(hdc, hollow)
                    (l, t, r, b), dot = frame
                    for inset, colour in enumerate(GLOW):
                        pen = win32gui.CreatePen(0, 2, win32api.RGB(*colour))
                        old = win32gui.SelectObject(hdc, pen)
                        win32gui.Rectangle(hdc, l + inset * 2, t + inset * 2, r - inset * 2, b - inset * 2)
                        win32gui.SelectObject(hdc, old)
                        win32gui.DeleteObject(pen)
                    if dot:
                        x, y = dot
                        pen = win32gui.CreatePen(0, 3, win32api.RGB(*GLOW[2]))
                        old = win32gui.SelectObject(hdc, pen)
                        win32gui.Ellipse(hdc, x - 13, y - 13, x + 13, y + 13)
                        fill = win32gui.CreateSolidBrush(win32api.RGB(*GLOW[2]))
                        win32gui.SelectObject(hdc, fill)
                        win32gui.Ellipse(hdc, x - 4, y - 4, x + 4, y + 4)
                        win32gui.SelectObject(hdc, hollow)
                        win32gui.SelectObject(hdc, old)
                        win32gui.DeleteObject(fill)
                        win32gui.DeleteObject(pen)
            finally:
                win32gui.EndPaint(hwnd, ps)

        def procedure(hwnd, message, wparam, lparam):
            if message == win32con.WM_PAINT:
                paint(hwnd)
                return 0
            if message == win32con.WM_MOUSEACTIVATE:
                return 3                                                              # never become the active window
            return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

        kind = win32gui.WNDCLASS()
        kind.lpfnWndProc = procedure
        kind.lpszClassName = 'OttoIndicator'
        kind.hInstance = win32api.GetModuleHandle(None)
        try:
            win32gui.RegisterClass(kind)
        except Exception:
            pass
        # layered + click-through + never takes focus + not in the taskbar or Alt-Tab + always on top
        own = win32gui.CreateWindowEx(0x80000 | 0x20 | 0x08000000 | 0x80 | 0x8, 'OttoIndicator', '', win32con.WS_POPUP,
                                      left, top, width, height, 0, 0, kind.hInstance, None)
        win32gui.SetLayeredWindowAttributes(own, key, 0, 1)                           # that colour is see-through
        if HIDE_FROM_CAPTURE:
            user32.SetWindowDisplayAffinity(own, 0x11)                                # left out of screenshots
        win.OTTO_WINDOWS.add(own)

        while True:
            try:
                while True:
                    command = commands.get_nowait()
                    state['seen'] = time.monotonic()
                    if command[0] == 'show':
                        state['target'] = command[1]
                    elif command[0] == 'point':
                        state['want'] = command[1]
                        state['at'] = state['at'] or command[1]
                    else:
                        state.update(target=None, want=None, at=None)
            except queue.Empty:
                pass
            if state['target'] and time.monotonic() - state['seen'] > 30:
                state.update(target=None, want=None, at=None)                         # never left on by accident
            frame = None
            if state['target']:
                try:
                    l, t, r, b = win32gui.GetWindowRect(state['target'])
                except Exception:
                    state['target'] = None
                else:
                    dot = None
                    if state['want']:
                        ax, ay = state['at']
                        wx, wy = state['want']
                        ax, ay = ax + (wx - ax) * 0.4, ay + (wy - ay) * 0.4            # glide, don't jump
                        state['at'] = (ax, ay)
                        dot = (round(ax) - left, round(ay) - top)
                    frame = ((l - left, t - top, r - left, b - top), dot)
            if frame != state['drawn']:
                state['drawn'] = frame
                win32gui.InvalidateRect(own, None, True)
            if bool(state['target']) != state['visible']:
                state['visible'] = bool(state['target'])
                win32gui.ShowWindow(own, 4 if state['visible'] else 0)                # 4 = show without activating
            win32gui.PumpWaitingMessages()
            time.sleep(0.04)
    except Exception:
        pass
