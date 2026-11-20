"""Skills: tools that do a whole job and check it themselves (docs/PLAN_NEXT.md, step 2).

Qwen picks the skill and fills in the details; plain code does the steps and checks each one. They are added to
the same menu as the small tools (core/tools.py), with the same shape (name, description, parameters, result),
and every call still goes through the safety gate in core/agent_safety.py.

Why: the live test on 12 Nov showed one-call jobs working every time (open Chrome, Google search) and chains of
small steps failing (YouTube: "lofi" typed three times into one box; Notepad: "Ctrl+S" typed as text, never saved).
"""
from __future__ import annotations

import re
import time
import urllib.parse

from core.tools import ToolResult, _action, _dry, tool

# ---- search --------------------------------------------------------------------------------------
WEB_SEARCH = {"google": "https://www.google.com/search?q={q}",
              "youtube": "https://www.youtube.com/results?search_query={q}"}
SEARCH_FIELD = {"google": "q", "youtube": "search_query"}     # where each site keeps the searched words
RESULTS_PATH = {"google": "/search", "youtube": "/results"}   # its results page (not settings with the same field)
SEARCH_WAIT = 6.0


@tool("search", "search Google, YouTube or Spotify where the user can see the results (for search, google, find "
      "a video/song). Opens the results page directly, nothing is typed. To PLAY a YouTube video, give play: it "
      "finds the video, opens it and says whether it saw it play",
      {"query": "what to search for", "where": "optional: google (default), youtube, spotify, or another app",
       "play": "optional, YouTube only: play this result, 1 = first, 2 = second...",
       "background": "optional, with play: yes only if the user said in the background"})
def search(ctx, query, where="google", play="", background="no"):
    where = (where or "google").lower().strip().removesuffix(".com")
    play = re.sub(r"\D", "", str(play or ""))
    if play and where == "youtube":
        played = _play(ctx, query, play, str(background or "no").lower().startswith("y"))
        if played:
            return played
    if ctx.dry_run:
        return _dry(ctx, f'search {where} for "{query}"')
    ctx.controls, ctx.look, ctx.hwnd = [], {}, None  # a new page: earlier reads and windows are stale
    if where in WEB_SEARCH:
        url = WEB_SEARCH[where].format(q=urllib.parse.quote_plus(query))
        opened = _action(ctx, "open_site", site=url)
        if not opened.ok:
            return opened
        ctx.app = "Google Chrome"
        shown_in = _shown(url, query, SEARCH_FIELD[where], RESULTS_PATH[where])
        if shown_in:
            ctx.hwnd = shown_in                     # the next read, look or scroll goes to this window
            return ToolResult(True, f'{where.title()} is showing results for "{query}".', {"searched": where})
        return ToolResult(False, f"I opened the {where.title()} search, but Chrome's address bar doesn't show it.")
    # Apps with their own search (Spotify, Steam, Settings...): the existing action checks what it can.
    return _action(ctx, "search_in_app", app=where, query=query)


def _play(ctx, query: str, which: str, background: bool) -> ToolResult | None:
    """A YouTube video found with the API and checked on screen (20 Nov live run: picking "the second video" from a
    screenshot clicked a Mix, then the sidebar). The model goes on afterwards, so the rest of a request still
    happens (Codex checkpoint C2); its "playing" is believed only if this saw the video play. None: no key, no
    quota or no connection, so the normal search runs and the video is picked from the page as before."""
    if ctx.dry_run:
        return _dry(ctx, f'play result {which} for "{query}" on YouTube' + (" in the background" if background else ""))
    ctx.controls, ctx.look, ctx.hwnd = [], {}, None
    res = _action(ctx, "play_video", query=query, which=which, background="yes" if background else "no")
    if not res.ok and res.observed.get("fallback"):
        return None
    if res.ok and not background:
        ctx.app, ctx.hwnd = "Google Chrome", res.observed.get("window") or None
    return res


def shows_search(address: str, host: str, path: str, field: str, query: str) -> bool:
    """This address is that site's results page for exactly this query. The whole query: "lofilofilofi" (12 Nov)
    is not "lofi", "c" is not "c++" and "banana bread pudding" is not "banana bread" (Codex, 20 Nov)."""
    parts = urllib.parse.urlparse(address if "://" in address else "https://" + address)
    asked = urllib.parse.parse_qs(parts.query).get(field, [""])[0]
    return ((parts.hostname or "").removeprefix("www.") == host and parts.path.rstrip("/") == path
            and " ".join(asked.casefold().split()) == " ".join(query.casefold().split()))


def _shown(url: str, query: str, field: str, path: str) -> int | None:
    """The Chrome window IN FRONT shows that site's results for these words, in the site's own search field (sites
    add their own extras to the address). Returns that window, or None. Not any Chrome window, and not the words
    anywhere in the address (Codex review 19 Nov: an old background search could pass)."""
    from hands import win
    from hands.web import chrome_addresses
    host = urllib.parse.urlparse(url).hostname.removeprefix("www.")
    wanted = " ".join(query.casefold().split())
    end = time.monotonic() + SEARCH_WAIT
    while True:
        hwnd = win.foreground()
        if any(shows_search(shown, host, path, field, wanted) for shown in chrome_addresses(only=hwnd)):
            return hwnd
        if time.monotonic() >= end:
            return None
        time.sleep(0.3)


# ---- save ----------------------------------------------------------------------------------------
UNSAVED = re.compile(r"^\s*\*|\*\s+-\s|[●•]|\bunsaved\b|\bnot saved\b", re.I)
SAVE_AS = re.compile(r"^\s*save (?:as|file)\b", re.I)
# Windows 11 Notepad names its tabs "notes.txt. Modified." / "notes.txt. Unmodified." (seen 12 Nov).
TAB_STATE = re.compile(r"^(.*?)\.?\s+(Modified|Unmodified)\.?$", re.I)
SAVE_WAIT = 3.0


@tool("save", "save the file in the window in front (presses ctrl+s and checks it really saved)", {})
def save(ctx):
    from core import agent_safety
    from hands import win
    if ctx.dry_run:
        return _dry(ctx, "press ctrl+s and check it saved")
    first = agent_safety.front(ctx)
    window = first.get("hwnd")
    before = _save_state(ctx, first)
    win.hotkey("ctrl+s")
    end = time.monotonic() + SAVE_WAIT
    while True:
        now = agent_safety.front(ctx)
        title = now.get("title", "")
        if SAVE_AS.search(title):
            return ToolResult(False, "The Save As window is open. Tell me the file name (and folder) to use.",
                              {"saved": False, "save_as": True})
        if window and now.get("hwnd") != window:
            # Another window came to the front: what it shows says nothing about this document (Codex review).
            return ToolResult(True, "I pressed Save, but another window came up, so I couldn't confirm it saved.",
                              {"saved": False})
        after = _save_state(ctx, now)
        if after["unsaved"] is False and (before["unsaved"] or after["tab"]):
            return ToolResult(True, "Saved (the window no longer shows unsaved changes).", {"saved": True})
        if time.monotonic() >= end:
            break
        time.sleep(0.25)
    if after["unsaved"]:
        return ToolResult(False, "It doesn't look saved yet: the window still shows unsaved changes.", {"saved": False})
    return ToolResult(True, "I pressed Save, but couldn't confirm it saved.", {"saved": False})


def _save_state(ctx, w: dict | None = None) -> dict:
    """{"unsaved": True/False/None (unknown), "tab": a tab told us}: from the title mark or the tab's own name,
    read from window `w` (the same lookup the caller checked; Codex re-review 20 Nov)."""
    from core import agent_safety
    w = w or agent_safety.front(ctx)
    title = w.get("title", "")
    for name in _tab_names(w.get("hwnd")):
        found = TAB_STATE.match(name)
        # The tab of THIS document: its name must be the whole document part of the title ("notes.txt" is not
        # "meeting notes.txt", Codex checkpoint C, 20 Nov).
        if found and found[1].strip() and found[1].strip().casefold() == _document(title).casefold():
            return {"unsaved": found[2].lower() == "modified", "tab": True}
    if UNSAVED.search(title):
        return {"unsaved": True, "tab": False}
    return {"unsaved": False if title else None, "tab": False}    # no mark: saved, or an app that shows none


def _document(title: str) -> str:
    """'*meeting notes.txt - Notepad' -> 'meeting notes.txt'."""
    return title.rsplit(" - ", 1)[0].lstrip("*●• ").strip()


def _tab_names(hwnd) -> list[str]:
    if not hwnd:
        return []
    try:
        from hands import ui_probe
        return [c["name"] for c in ui_probe.list_controls(hwnd, limit=200) if c.get("type") == "TabItem"]
    except Exception:
        return []
