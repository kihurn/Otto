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
SEARCH_WAIT = 6.0


@tool("search", "search Google, YouTube or Spotify where the user can see the results (for search, google, find "
      "a video/song). Opens the results page directly, nothing is typed",
      {"query": "what to search for", "where": "optional: google (default), youtube, spotify, or another app"})
def search(ctx, query, where="google"):
    where = (where or "google").lower().strip().removesuffix(".com")
    if ctx.dry_run:
        return _dry(ctx, f'search {where} for "{query}"')
    ctx.controls, ctx.look = [], {}                 # a new page: earlier reads are stale
    if where in WEB_SEARCH:
        url = WEB_SEARCH[where].format(q=urllib.parse.quote_plus(query))
        opened = _action(ctx, "open_site", site=url)
        if not opened.ok:
            return opened
        ctx.app = "Google Chrome"
        if _shown(url, query):
            return ToolResult(True, f'{where.title()} is showing results for "{query}".', {"searched": where})
        return ToolResult(False, f"I opened the {where.title()} search, but Chrome's address bar doesn't show it.")
    # Apps with their own search (Spotify, Steam, Settings...): the existing action checks what it can.
    return _action(ctx, "search_in_app", app=where, query=query)


def _shown(url: str, query: str) -> bool:
    """Chrome's address bar shows that site with the searched words (sites add their own extras to the address)."""
    from hands.web import chrome_addresses
    host = urllib.parse.urlparse(url).hostname.removeprefix("www.")
    words = re.findall(r"\w+", query.casefold())
    end = time.monotonic() + SEARCH_WAIT
    while True:
        for shown in chrome_addresses():
            parts = urllib.parse.urlparse(shown if "://" in shown else "https://" + shown)
            seen = set(re.findall(r"\w+", urllib.parse.unquote_plus(parts.query).casefold()))
            # Whole words: "lofilofilofi" (typed three times, 12 Nov) is not a search for "lofi".
            if (parts.hostname or "").removeprefix("www.") == host and all(w in seen for w in words):
                return True
        if time.monotonic() >= end:
            return False
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
    before = _save_state(ctx)
    win.hotkey("ctrl+s")
    end = time.monotonic() + SAVE_WAIT
    while True:
        title = agent_safety.front(ctx).get("title", "")
        if SAVE_AS.search(title):
            return ToolResult(False, "The Save As window is open. Tell me the file name (and folder) to use.",
                              {"saved": False, "save_as": True})
        after = _save_state(ctx)
        if after["unsaved"] is False and (before["unsaved"] or after["tab"]):
            return ToolResult(True, "Saved (the window no longer shows unsaved changes).", {"saved": True})
        if time.monotonic() >= end:
            break
        time.sleep(0.25)
    if after["unsaved"]:
        return ToolResult(False, "It doesn't look saved yet: the window still shows unsaved changes.", {"saved": False})
    return ToolResult(True, "I pressed Save, but couldn't confirm it saved.", {"saved": False})


def _save_state(ctx) -> dict:
    """{"unsaved": True/False/None (unknown), "tab": a tab told us}: from the title mark or the tab's own name."""
    from core import agent_safety
    w = agent_safety.front(ctx)
    title = w.get("title", "")
    for name in _tab_names(w.get("hwnd")):
        found = TAB_STATE.match(name)
        if found and found[1].strip() and found[1].strip().casefold() in title.casefold():
            return {"unsaved": found[2].lower() == "modified", "tab": True}
    if UNSAVED.search(title):
        return {"unsaved": True, "tab": False}
    return {"unsaved": False if title else None, "tab": False}    # no mark: saved, or an app that shows none


def _tab_names(hwnd) -> list[str]:
    if not hwnd:
        return []
    try:
        from hands import ui_probe
        return [c["name"] for c in ui_probe.list_controls(hwnd, limit=200) if c.get("type") == "TabItem"]
    except Exception:
        return []
