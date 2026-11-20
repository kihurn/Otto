"""YouTube without the screen (background mode, step 4c): find a video with the YouTube Data API, then open it in
its own Chrome window that is minimised once it plays. The key is OTTO_YOUTUBE_API_KEY in .env (from the user's
Google Cloud project, with the YouTube Data API turned on). It is sent in a header, never in an address, so it
can't end up in a log. One search costs 100 of the 10,000 free units a day (about 100 searches)."""

from __future__ import annotations

import html
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from hands import win
from hands.registry import UNDOABLE, Result, action

SEARCH = "https://www.googleapis.com/youtube/v3/search"
WATCH = "https://www.youtube.com/watch?v={}"
PLAY_WAIT = 8.0              # seconds for the page to start playing before its window is minimised


class YouTubeError(Exception):
    pass


def key() -> str | None:
    return (os.environ.get("OTTO_YOUTUBE_API_KEY") or "").strip() or None


def find_videos(query: str, count: int = 5) -> list[tuple[str, str]]:
    """[(video id, title)] of YouTube's top results, in order, without live streams. Only single videos are asked
    for, so Mixes and playlists never come back. Raises YouTubeError with a sentence for the user."""
    params = urllib.parse.urlencode({"part": "snippet", "type": "video", "maxResults": count, "q": query})
    req = urllib.request.Request(f"{SEARCH}?{params}", headers={"X-Goog-Api-Key": key() or ""})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            reason = (json.load(e).get("error", {}).get("errors") or [{}])[0].get("reason", "")
        except Exception:
            reason = ""
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise YouTubeError("YouTube's daily search limit is used up; it resets at midnight Pacific time.")
        if e.code in (400, 401, 403):
            raise YouTubeError("YouTube refused the key. Check OTTO_YOUTUBE_API_KEY, and that the YouTube Data API "
                               "is turned on in your Google Cloud project.")
        raise YouTubeError(f"YouTube answered with error {e.code}.")
    except (urllib.error.URLError, OSError, ValueError):
        raise YouTubeError("I couldn't reach YouTube.")
    found = []
    for item in data.get("items") or []:
        vid, snippet = (item.get("id") or {}).get("videoId"), item.get("snippet") or {}
        if vid and snippet.get("liveBroadcastContent", "none") == "none":
            found.append((vid, html.unescape(snippet.get("title") or "the video")))
    return found


def find_video(query: str, which: int = 1) -> tuple[str, str] | None:
    """The which-th result (1 = first), or None."""
    found = find_videos(query, max(5, which + 3))
    return found[which - 1] if len(found) >= which else None


def _chrome_playing() -> set[str]:
    """Titles of what Chrome is playing right now (Windows' media controls)."""
    from hands import media
    return {s["title"] for s in media.sessions() or [] if s["status"] == media.PLAYING and "chrome" in s["app"].casefold()}


def shows_video(address: str, vid: str) -> bool:
    parts = urllib.parse.urlparse(address if "://" in address else "https://" + address)
    return ((parts.hostname or "").removeprefix("www.").removeprefix("m.") == "youtube.com" and parts.path == "/watch"
            and urllib.parse.parse_qs(parts.query).get("v") == [vid])


SHOW_WAIT = 6.0
ORDINAL = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}


@action("play_video", UNDOABLE, {"query": "what video to play", "which": "which result, 1 = first (default)",
                                 "background": "yes (default): minimised; no: in front"},
        lambda query, which="1", background="yes": f"play the {ORDINAL.get(int(which) if str(which).isdigit() else 1, which)} {query} video on "
        "YouTube" + (" in the background" if str(background).lower().startswith("y") else ""))
def play_video(query: str, which: str = "1", background: str = "yes") -> Result:
    """No key, no quota or no connection: data["fallback"] is set, so the agent can search and click instead."""
    if not key():
        return Result(False, "To find videos without the screen I need a YouTube key: add OTTO_YOUTUBE_API_KEY to "
                             "your .env file.", {"fallback": True})
    n = max(1, min(10, int(which) if str(which).strip().isdigit() else 1))
    try:
        found = find_video(query, n)
    except YouTubeError as e:
        return Result(False, str(e), {"fallback": True})
    if not found:
        return Result(False, f"I couldn't find a {query} video on YouTube.")
    vid, title = found
    from hands import web
    url = WATCH.format(vid)
    if not str(background).lower().startswith("y"):
        web.open_in_browser(url)
        end = time.monotonic() + SHOW_WAIT                 # done only when the front window shows THAT video
        while win.IS_WINDOWS:
            front = win.foreground()
            if any(shows_video(a, vid) for a in web.chrome_addresses(only=front)):
                return Result(True, f"Playing {title}.", {"video": vid, "window": front})
            if time.monotonic() >= end:
                break
            time.sleep(0.3)
        return Result(False, f"I opened {title}, but Chrome doesn't show it in front.", {"video": vid})
    before = _chrome_playing() if win.IS_WINDOWS else set()       # something else already playing doesn't count
    started = lambda: bool(_chrome_playing() - before)
    with win.screen_borrowed("chrome.exe") as borrowed:
        web.open_in_browser(url, new_window=True)
        # Minimised before it starts, Chrome may never start it, so the window stays up until it plays (max 8 s).
        end = time.monotonic() + PLAY_WAIT
        while win.IS_WINDOWS and not started() and time.monotonic() < end:
            time.sleep(0.3)
    data = {"video": vid, "window": borrowed.new[0] if borrowed.new else 0}
    if win.IS_WINDOWS and started():
        return Result(True, f"Playing {title} in the background.", data)
    return Result(True, f"I opened {title} in the background, but I couldn't confirm it's playing.", data)
