"""Global hotkeys: hold-to-talk and mute, working while any app is in front."""

from __future__ import annotations

_listener = None


class ChordState:
    """Track physical keys so repeats and either modifier release are handled once."""
    def __init__(self, push, mute, down, up, toggle):
        self.push, self.mute = set(push), set(mute)
        self.down, self.up, self.toggle = down, up, toggle
        self.pressed = set()
        self.push_active = self.mute_active = False

    def update(self, key, pressed):
        if pressed:
            self.pressed.add(key)
        else:
            self.pressed.discard(key)
        # Left/right variants count as the same modifier, but releases remain physical.
        names = {str(k).removeprefix('Key.').removesuffix('_l').removesuffix('_r') for k in self.pressed}
        push = self.push <= names
        mute = self.mute <= names
        if push != self.push_active:
            self.push_active = push
            (self.down if push else self.up)()
        if mute and not self.mute_active:
            self.toggle()
        self.mute_active = mute


def _chord(name):
    parts = [p.strip().lower() for p in name.split('+')]
    if not parts or any(not p for p in parts):
        raise ValueError('Empty hotkey')
    for part in parts:
        _key_from_name(part)
    return parts


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
        push, mute = _chord(push_key), _chord(mute_key)
    except Exception:
        return False
    state = ChordState(push, mute, on_push_down, on_push_up, on_mute)

    def normalized(key):
        return key.char.lower() if getattr(key, 'char', None) else str(key)

    def press(key):
        state.update(normalized(key), True)

    def release(key):
        state.update(normalized(key), False)

    _listener = keyboard.Listener(on_press=press, on_release=release)
    _listener.daemon = True
    _listener.start()
    return True


def stop() -> None:
    if _listener:
        _listener.stop()
