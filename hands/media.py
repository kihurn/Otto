"""Music and volume.

- Spotify (Premium): exact songs/artists/albums/playlists, Liked Songs, what's playing, through
  Spotify's official API (connectors/spotify.py).
- Any other player (YouTube in Chrome, etc.): Windows' own media controls, so Otto can see whether
  something is actually playing and reply honestly.
- Media keys only as a last resort.
"""

from __future__ import annotations

import asyncio
import time

from hands import win
from hands.registry import READ, UNDOABLE, Result, action

# ---------------------------------------------------------------------------------------------
# Windows media sessions (what's playing in any app)
# ---------------------------------------------------------------------------------------------
PLAYING, PAUSED = 4, 5


def _run(coro):
    try:
        return asyncio.run(coro)
    except Exception:
        return None


async def _session_info():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M

    mgr = await M.request_async()
    sessions = list(mgr.get_sessions())
    cur = mgr.get_current_session()
    out = []
    for s in sessions:
        try:
            props = await s.try_get_media_properties_async()
            status = int(s.get_playback_info().playback_status)
        except Exception:
            props, status = None, 0
        out.append({"app": s.source_app_user_model_id or "", "title": getattr(props, "title", "") or "",
                    "artist": getattr(props, "artist", "") or "", "status": status,
                    "current": bool(cur and s.source_app_user_model_id == cur.source_app_user_model_id)})
    return out


async def _session_do(what: str, app_hint: str = ""):
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M

    mgr = await M.request_async()
    target = None
    if app_hint:
        target = next((s for s in mgr.get_sessions() if app_hint.lower() in (s.source_app_user_model_id or "").lower()), None)
    target = target or mgr.get_current_session()
    if not target:
        return False
    fn = {"play": target.try_play_async, "pause": target.try_pause_async, "toggle": target.try_toggle_play_pause_async,
          "next": target.try_skip_next_async, "previous": target.try_skip_previous_async}[what]
    return bool(await fn())


def sessions() -> list[dict] | None:
    """None if Windows' media controls aren't available (package missing)."""
    return _run(_session_info())


def playing_anywhere() -> dict | None:
    for s in sessions() or []:
        if s["status"] == PLAYING:
            return s
    return None


# ---------------------------------------------------------------------------------------------
# Spotify helpers
# ---------------------------------------------------------------------------------------------

def _spotify():
    from connectors import spotify
    if not spotify.configured() or not spotify.signed_in():
        return None
    return spotify


def _launch_spotify():
    from core.action_runtime import check
    check()
    from hands.apps import open_app
    open_app("Spotify")


@action("play_music", UNDOABLE, {"query": "song, artist, album or playlist name", "kind": "track/artist/album/playlist/auto",
                                 "artist": "optional artist, when the query is a song"},
        lambda query, kind="auto", artist="": f"play {query}" + (f" by {artist}" if artist else "") + " on Spotify",
        for_brain=True, note="plays music on Spotify; prefer this over searching and clicking")
def play_music(query: str, kind: str = "auto", artist: str = "") -> Result:
    sp = _spotify()
    if not sp:
        from hands.apps import search_in_app
        res = search_in_app("Spotify", f"{query} {artist}".strip())
        res.say += " (Connect Spotify with  otto spotify  so I can press play for you.)"
        return res
    try:
        found = sp.best_match(query, kind or "auto", artist)
        if not found:
            return Result(False, f"I couldn't find {query} on Spotify.")
        k, uri, item = found
        dev = sp.ensure_device(_launch_spotify)
        if not dev:
            return Result(False, "Spotify didn't show up as a player. Is the Spotify app signed in?")
        sp.play(uri, k, dev["id"])
        return Result(True, f"Playing {sp.describe(k, item)}.")
    except sp.SpotifyError as e:
        return Result(False, f"Spotify said: {e}")


@action("play_liked", UNDOABLE, {}, lambda: "play your Liked Songs on Spotify", for_brain=True)
def play_liked() -> Result:
    sp = _spotify()
    if not sp:
        from hands.apps import open_link
        open_link("spotify:collection:tracks")
        return Result(True, "Opened your Liked Songs. (Connect Spotify with  otto spotify  so I can press play.)")
    try:
        dev = sp.ensure_device(_launch_spotify)
        if not dev:
            return Result(False, "Spotify didn't show up as a player. Is the Spotify app signed in?")
        sp.play_liked(dev["id"])
        return Result(True, "Playing your Liked Songs on shuffle.")
    except sp.SpotifyError as e:
        return Result(False, f"Spotify said: {e}")


@action("now_playing", READ, {}, lambda: "check what's playing")
def now_playing() -> Result:
    sp = _spotify()
    if sp:
        try:
            np = sp.now_playing()
            if np and np["playing"]:
                return Result(True, f"{np['title']} by {np['artist']}.")
        except sp.SpotifyError:
            pass
    s = playing_anywhere()
    if s and s["title"]:
        return Result(True, f"{s['title']}" + (f" by {s['artist']}" if s["artist"] else "") + ".")
    return Result(True, "Nothing's playing right now.")


def _verify_state(want_playing: bool, before: bool | None) -> bool | None:
    """Check whether something is playing now. None = can't tell."""
    time.sleep(0.6)
    sp = _spotify()
    if sp:
        try:
            st = sp.is_playing()
            if st is not None:
                return st == want_playing
        except Exception:
            pass
    ss = sessions()
    if ss is None:
        return None
    now = any(s["status"] == PLAYING for s in ss)
    return now == want_playing


@action("media_key", UNDOABLE, {"key": "play, pause, play_pause, next, previous or mute"},
        lambda key: {"play": "play", "pause": "pause", "play_pause": "play/pause", "next": "skip to the next track",
                     "previous": "go to the previous track", "mute": "mute/unmute"}.get(key, key))
def media_key(key: str) -> Result:
    if key == "mute":
        win.press_vk(win.VK["mute"])
        return Result(True, "Toggled mute.")
    ss = sessions()
    playing = any(s["status"] == PLAYING for s in ss) if ss is not None else None
    if key == "play_pause":
        key = "pause" if playing else "play"
    sp = _spotify()

    if key in ("play", "pause"):
        if key == "pause" and playing is False:
            return Result(True, "Nothing's playing.")
        if key == "play" and playing:
            return Result(True, "It's already playing.")
        done = False
        if sp:
            try:
                sp.control("resume" if key == "play" else "pause")
                done = True
            except Exception:
                done = False
        if not done and ss:
            done = bool(_run(_session_do(key)))
        if not done:
            win.press_vk(win.VK["play_pause"])
        ok = _verify_state(key == "play", playing)
        if ok is False:
            if key == "play":
                return Result(False, "Nothing is loaded to play. Say \"play my music\" for your Liked Songs, "
                                     "or tell me a song.", {"offer_liked": True})
            return Result(False, "I couldn't pause it.")
        return Result(True, "Playing." if key == "play" else "Paused.")

    if key in ("next", "previous"):
        done = False
        if sp:
            try:
                sp.control(key)
                done = True
            except Exception:
                pass
        if not done and ss:
            done = bool(_run(_session_do(key)))
        if not done:
            win.press_vk(win.VK[key])
        time.sleep(0.8)
        np = now_playing()
        return Result(True, ("Next: " if key == "next" else "Back to: ") + np.say if np.say != "Nothing's playing right now."
                      else ("Skipped." if key == "next" else "Went back."))
    return Result(False, f"I don't know the media key {key}.")


# ---------------------------------------------------------------------------------------------
# Volume (Windows master volume)
# ---------------------------------------------------------------------------------------------

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


def endpoint_id() -> str | None:
    try:
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
        return str(device.id)
    except Exception:
        return None


@action('get_volume', READ, {}, lambda: 'check the current volume', for_brain=True)
def get_volume() -> Result:
    now = current_volume()
    return Result(now is not None, f'Volume {now}%.' if now is not None else 'I could not read the volume.',
                  {'volume': now})


@action("set_volume", UNDOABLE, {"level": "0 to 100"}, lambda level: f"set the volume to {level}%", for_brain=True)
def set_volume(level) -> Result:
    level = max(0, min(100, int(float(level))))
    try:
        ep = _endpoint()
        ep.SetMute(0, None)
        ep.SetMasterVolumeLevelScalar(level / 100, None)
        now = current_volume()
        return Result(True, f"Volume {now if now is not None else level}%.")
    except Exception:
        win.press_vk(win.VK["volume_down"], 50)
        win.press_vk(win.VK["volume_up"], level // 2)
        return Result(True, f"Volume about {level}%.")


@action("change_volume", UNDOABLE, {"step": "positive = louder, negative = quieter, in %"},
        lambda step: ("turn it up" if int(float(step)) > 0 else "turn it down"))
def change_volume(step) -> Result:
    step = int(float(step))
    now = current_volume()
    if now is not None:
        return set_volume(max(0, min(100, now + step)))
    win.press_vk(win.VK["volume_up" if step > 0 else "volume_down"], max(1, abs(step) // 2))
    return Result(True, "Louder." if step > 0 else "Quieter.")
