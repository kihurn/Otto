"""Media keys and volume. Media keys work with Spotify, YouTube in Chrome, and most players."""

from __future__ import annotations

from hands import win
from hands.registry import UNDOABLE, Result, action

_SAY = {"play_pause": "Done.", "next": "Next track.", "previous": "Previous track.", "mute": "Toggled mute."}


@action("media_key", UNDOABLE, {"key": "play_pause, next, previous or mute"},
        lambda key: {"play_pause": "play/pause", "next": "skip to the next track",
                     "previous": "go to the previous track", "mute": "mute/unmute"}.get(key, key))
def media_key(key: str) -> Result:
    if key not in win.VK:
        return Result(False, f"I don't know the media key {key}.")
    win.press_vk(win.VK[key])
    return Result(True, _SAY.get(key, "Done."))


def _endpoint():
    from pycaw.pycaw import AudioUtilities

    speakers = AudioUtilities.GetSpeakers()
    if hasattr(speakers, "EndpointVolume"):           # newer pycaw
        return speakers.EndpointVolume
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def current_volume() -> int | None:
    try:
        return round(_endpoint().GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return None


@action("set_volume", UNDOABLE, {"level": "0 to 100"}, lambda level: f"set the volume to {level}%")
def set_volume(level) -> Result:
    level = max(0, min(100, int(float(level))))
    try:
        ep = _endpoint()
        ep.SetMute(0, None)
        ep.SetMasterVolumeLevelScalar(level / 100, None)
        return Result(True, f"Volume set to {level}%.")
    except Exception:
        # Fallback: volume keys move about 2% per press
        win.press_vk(win.VK["volume_down"], 50)
        win.press_vk(win.VK["volume_up"], level // 2)
        return Result(True, f"Volume set to about {level}%.")


@action("change_volume", UNDOABLE, {"step": "positive = louder, negative = quieter, in %"},
        lambda step: ("turn it up" if int(step) > 0 else "turn it down"))
def change_volume(step) -> Result:
    step = int(float(step))
    now = current_volume()
    if now is not None:
        return set_volume(max(0, min(100, now + step)))
    win.press_vk(win.VK["volume_up" if step > 0 else "volume_down"], max(1, abs(step) // 2))
    return Result(True, "Louder." if step > 0 else "Quieter.")
