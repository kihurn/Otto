"""Global hotkeys: hold-to-talk and mute, working while any app is in front."""

from __future__ import annotations

import threading

_listener = None


def _key_from_name(name: str):
    from pynput import keyboard

    name = (name or "").lower().strip()
    if hasattr(keyboard.Key, name):
        return getattr(keyboard.Key, name)
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    raise ValueError(f"unknown key {name!r}")


def start(push_key: str, mute_key: str, on_push_down, on_push_up, on_mute) -> bool:
    """Returns False if hotkeys aren't available (pynput missing)."""
    global _listener
    try:
        from pynput import keyboard
        push, mute = _key_from_name(push_key), _key_from_name(mute_key)
    except Exception:
        return False
    held = threading.Event()

    def press(key):
        if key == push and not held.is_set():
            held.set()
            on_push_down()
        elif key == mute:
            on_mute()

    def release(key):
        if key == push and held.is_set():
            held.clear()
            on_push_up()

    _listener = keyboard.Listener(on_press=press, on_release=release)
    _listener.daemon = True
    _listener.start()
    return True


def stop() -> None:
    if _listener:
        _listener.stop()
