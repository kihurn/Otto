"""A visible sign that Otto is operating an app: a soft blue glow around that window and a small Otto pointer
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

COLOUR = (24, 119, 201)        # Otto's blue, #1877c9 (red, green, blue)
CORNER = 8                     # Windows 11 rounds window corners by about 8 pixels; the glow follows them
GLOW_WIDTH = 18                # how many pixels the glow takes to fade away from the window's edge
FADE_SECONDS = 0.25            # fade in when Otto starts on a window, fade out when it finishes
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


def looking(hwnd: int, on: bool = True) -> None:
    """While Otto takes a screenshot of this window and Qwen studies it: a small "Otto is looking" badge.
    (The overlay is left out of screenshots, so the badge never ends up in the picture.)"""
    if _enabled():
        _send(('show', hwnd))
        _send(('looking', bool(on)))


def hide() -> None:
    if _commands is not None:
        _send(('hide',))


def render(size, frame):
    """The overlay picture: see-through everywhere except a glow that is brightest at the window's edge and
    fades towards its middle, plus the pointer. Returns bytes in the layout Windows wants."""
    import numpy as np
    from PIL import Image, ImageDraw

    image = Image.new('RGBA', size, (0, 0, 0, 0))
    if frame:
        draw = ImageDraw.Draw(image)
        (l, t, r, b), dot = frame[:2]
        badge = len(frame) > 2 and frame[2]
        for step in range(GLOW_WIDTH):
            strength = (1 - step / GLOW_WIDTH) ** 2                     # quick fall-off: bright edge, soft inside
            draw.rounded_rectangle((l + step, t + step, r - 1 - step, b - 1 - step), radius=max(0, CORNER - step),
                                   outline=COLOUR + (int(235 * strength),))
        if badge:
            _badge(draw, (l + r) // 2, t + GLOW_WIDTH + 4, "Otto is looking")
        if dot:
            x, y = dot
            for grow, alpha in ((6, 40), (4, 80), (2, 140)):            # a soft halo around the ring
                draw.ellipse((x - 13 - grow, y - 13 - grow, x + 13 + grow, y + 13 + grow), outline=COLOUR + (alpha,), width=2)
            draw.ellipse((x - 13, y - 13, x + 13, y + 13), outline=COLOUR + (255,), width=3)
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 255, 255, 255), outline=COLOUR + (255,))
    pixels = np.asarray(image, dtype=np.uint16)
    alpha = pixels[..., 3:4]
    colour = (pixels[..., :3] * alpha // 255)[..., ::-1]                # Windows wants blue-green-red, pre-faded
    return np.concatenate([colour, alpha], axis=2).astype(np.uint8).tobytes()


def _badge(draw, centre_x: int, top: int, text: str) -> None:
    """A small rounded label in Otto's blue, centred at the top of the window."""
    from PIL import ImageFont
    try:
        font = ImageFont.truetype("segoeui.ttf", 15)
    except Exception:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    left, right = centre_x - w // 2 - 14, centre_x + w // 2 + 14
    draw.rounded_rectangle((left, top, right, top + h + 14), radius=(h + 14) // 2, fill=COLOUR + (235,))
    draw.text((centre_x - w // 2, top + 7 - box[1]), text, font=font, fill=(255, 255, 255, 255))


def _run(commands: queue.Queue) -> None:
    """The overlay's own thread: one plain Windows window covering the screen, see-through except for the
    glow and pointer. (A plain window is used because a Tk window grabs the keyboard when shown.)"""
    try:
        import ctypes
        from ctypes import wintypes
        import win32api
        import win32con
        import win32gui
        from hands import win

        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)          # all monitors together
        width, height = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)

        kind = win32gui.WNDCLASS()
        kind.lpfnWndProc = lambda hwnd, message, wparam, lparam: (
            3 if message == win32con.WM_MOUSEACTIVATE else win32gui.DefWindowProc(hwnd, message, wparam, lparam))
        kind.lpszClassName = 'OttoIndicator'
        kind.hInstance = win32api.GetModuleHandle(None)
        try:
            win32gui.RegisterClass(kind)
        except Exception:
            pass
        # layered + click-through + never takes focus + not in the taskbar or Alt-Tab + always on top
        own = win32gui.CreateWindowEx(0x80000 | 0x20 | 0x08000000 | 0x80 | 0x8, 'OttoIndicator', '', win32con.WS_POPUP,
                                      left, top, width, height, 0, 0, kind.hInstance, None)
        if HIDE_FROM_CAPTURE:
            user32.SetWindowDisplayAffinity(own, 0x11)                                # left out of screenshots
        win.OTTO_WINDOWS.add(own)

        # A picture buffer Windows can blend onto the screen with per-pixel see-through.
        class Header(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                        ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                        ('image_size', wintypes.DWORD), ('xppm', wintypes.LONG), ('yppm', wintypes.LONG),
                        ('used', wintypes.DWORD), ('important', wintypes.DWORD)]

        class Blend(ctypes.Structure):
            _fields_ = [('op', ctypes.c_byte), ('flags', ctypes.c_byte), ('alpha', ctypes.c_ubyte), ('format', ctypes.c_byte)]

        user32.GetDC.restype = gdi32.CreateCompatibleDC.restype = gdi32.CreateDIBSection.restype = ctypes.c_void_p
        gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
        gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.UpdateLayeredWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        screen = user32.GetDC(None)
        memory = gdi32.CreateCompatibleDC(screen)
        header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)   # negative height = top row first
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(memory, bitmap)
        where, extent, origin = wintypes.POINT(left, top), wintypes.SIZE(width, height), wintypes.POINT(0, 0)

        def present(alpha: int) -> None:
            blend = Blend(0, 0, max(0, min(255, alpha)), 1)
            user32.UpdateLayeredWindow(own, screen, ctypes.byref(where), ctypes.byref(extent), memory,
                                       ctypes.byref(origin), 0, ctypes.byref(blend), 2)

        state = {'target': None, 'want': None, 'at': None, 'seen': time.monotonic(), 'drawn': None,
                 'level': 0.0, 'shown': False}
        while True:
            try:
                while True:
                    command = commands.get_nowait()
                    state['seen'] = time.monotonic()
                    if command[0] == 'show':
                        state['target'] = command[1]
                    elif command[0] == 'looking':
                        state['looking'] = command[1]
                    elif command[0] == 'point':
                        state['want'] = command[1]
                        state['at'] = state['at'] or command[1]
                    else:
                        state.update(target=None, want=None, at=None, looking=False)
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
                    # A maximised window pokes a few pixels past the screen; keep the glow where it can be seen.
                    l, t = max(l, left), max(t, top)
                    r, b = min(r, left + width), min(b, top + height)
                    dot = None
                    if state['want']:
                        ax, ay = state['at']
                        wx, wy = state['want']
                        ax, ay = ax + (wx - ax) * 0.4, ay + (wy - ay) * 0.4            # glide, don't jump
                        state['at'] = (ax, ay)
                        dot = (round(ax) - left, round(ay) - top)
                    frame = ((l - left, t - top, r - left, b - top), dot, bool(state.get('looking')))
            goal = 1.0 if frame else 0.0
            step = 0.04 / FADE_SECONDS
            level = min(goal, state['level'] + step) if goal > state['level'] else max(goal, state['level'] - step)
            redraw = frame is not None and frame != state['drawn']                    # while fading out, keep the last picture
            if redraw:
                state['drawn'] = frame
                data = render((width, height), frame)
                ctypes.memmove(bits, data, len(data))
            if redraw or level != state['level']:
                state['level'] = level
                if level > 0 and not state['shown']:
                    win32gui.ShowWindow(own, 4)                                       # 4 = show without activating
                    state['shown'] = True
                present(int(255 * level))
                if level == 0 and state['shown']:
                    win32gui.ShowWindow(own, 0)
                    state['shown'] = False
                    state['drawn'] = None
            win32gui.PumpWaitingMessages()
            time.sleep(0.04)
    except Exception:
        pass
