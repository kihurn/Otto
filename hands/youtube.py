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


def find_video(query: str) -> tuple[str, str] | None:
    """(video id, title) of YouTube's top result, or None. Raises YouTubeError with a sentence for the user."""
    params = urllib.parse.urlencode({"part": "snippet", "type": "video", "maxResults": 1, "q": query})
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
    for item in data.get("items") or []:
        vid = (item.get("id") or {}).get("videoId")
        if vid:
            return vid, html.unescape((item.get("snippet") or {}).get("title") or "the video")
    return None


def _chrome_playing() -> set[str]:
    """Titles of what Chrome is playing right now (Windows' media controls)."""
    from hands import media
    return {s["title"] for s in media.sessions() or [] if s["status"] == media.PLAYING and "chrome" in s["app"].casefold()}


@action("play_video", UNDOABLE, {"query": "what video to play"},
        lambda query: f"play a {query} video on YouTube in the background")
def play_video(query: str) -> Result:
    if not key():
        return Result(False, "To play videos in the background I need a YouTube key: add OTTO_YOUTUBE_API_KEY to "
                             "your .env file.")
    try:
        found = find_video(query)
    except YouTubeError as e:
        return Result(False, str(e))
    if not found:
        return Result(False, f"I couldn't find a {query} video on YouTube.")
    vid, title = found
    from hands import web
    before = _chrome_playing() if win.IS_WINDOWS else set()       # something else already playing doesn't count
    started = lambda: bool(_chrome_playing() - before)
    with win.screen_borrowed("chrome.exe") as borrowed:
        web.open_in_browser(WATCH.format(vid), new_window=True)
        # Minimised before it starts, Chrome may never start it, so the window stays up until it plays (max 8 s).
        end = time.monotonic() + PLAY_WAIT
        while win.IS_WINDOWS and not started() and time.monotonic() < end:
            time.sleep(0.3)
    playing = win.IS_WINDOWS and started()
    data = {"video": vid, "window": borrowed.new[0] if borrowed.new else 0}
    if playing:
        return Result(True, f"Playing {title} in the background.", data)
    return Result(True, f"I opened {title} in the background, but I couldn't confirm it's playing.", data)
