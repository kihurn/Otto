"""Websites and web searches, always in Chrome (falls back to the default browser if Chrome is missing)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

from core.config import SITES_FILE, load_json
from hands.registry import UNDOABLE, Result, action

_CHROME_PATHS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
]


def chrome_path() -> str | None:
    for p in _CHROME_PATHS:
        if p.is_file():
            return str(p)
    return shutil.which("chrome")


def open_in_browser(url: str) -> None:
    chrome = chrome_path()
    if chrome:
        subprocess.Popen([chrome, url])
    else:
        webbrowser.open(url)


def sites() -> dict[str, str]:
    return {k.lower(): v for k, v in load_json(SITES_FILE, {}).items()}


def site_url(name: str) -> str | None:
    """'youtube' -> https://www.youtube.com, 'github.com' -> https://github.com, else None."""
    if re.fullmatch(r"https?://\S+", name.strip(), re.I):
        return name.strip()                  # already a full address: open it as it is, never Google it
    n = name.lower().strip().removeprefix("the ").removesuffix(" website").removesuffix(" site").strip()
    known = sites()
    if n in known:
        return known[n]
    from rapidfuzz import fuzz, process
    found = process.extractOne(n, list(known), scorer=fuzz.ratio)
    if found and found[1] >= 88:
        return known[found[0]]
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?", n):
        return "https://" + n
    return None


# "Open a new tab" opens Google in a new tab. Chrome ignores chrome://newtab when it is passed from outside
# and opens a whole new window instead (seen on the user's PC, 11 Nov 2026).
NEW_TAB = "https://www.google.com"


def same_page(shown: str, wanted: str) -> bool:
    """Does the text in Chrome's address bar match the address Otto asked for?
    Same site is enough (sites redirect to longer addresses); a Google search must also show the same words."""
    seen = urllib.parse.urlparse(shown if "://" in shown else "https://" + shown)
    want = urllib.parse.urlparse(wanted)

    def host(parts) -> str:
        return (parts.hostname or "").removeprefix("www.")

    if not host(seen) or host(seen) != host(want):
        return False
    asked = urllib.parse.parse_qs(want.query).get("q")
    if want.path == "/search" and asked:
        return seen.path == "/search" and urllib.parse.parse_qs(seen.query).get("q") == asked
    return True


def chrome_addresses() -> list[str]:
    """What the address bar of each open Chrome window shows right now. Read-only; never logged."""
    from hands import win
    from hands.window_control import chrome_control_ok
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.uia_defines import IUIA
    from pywinauto.uia_element_info import UIAElementInfo

    uia = IUIA()
    wanted = uia.iuia.CreateAndCondition(
        uia.iuia.CreatePropertyCondition(uia.UIA_dll.UIA_ControlTypePropertyId, uia.UIA_dll.UIA_EditControlTypeId),
        uia.iuia.CreatePropertyCondition(uia.UIA_dll.UIA_NamePropertyId, "Address and search bar"))
    found = []
    for window in win.windows():
        if window["exe"].casefold() != "chrome.exe":
            continue
        try:
            bar = uia.iuia.ElementFromHandle(window["hwnd"]).FindFirst(uia.UIA_dll.TreeScope_Descendants, wanted)
            control = UIAWrapper(UIAElementInfo(bar)) if bar else None
            if control and chrome_control_ok(control):  # Chrome's own bar, never a look-alike inside a page
                found.append(control.iface_value.CurrentValue or "")
        except Exception:
            continue
    return found


def shown_in_chrome(url: str, wait: float = 4.0) -> bool:
    """Watch Chrome's address bar for a few seconds; True once a window shows the page Otto opened."""
    import time
    from core.action_runtime import check

    end = time.monotonic() + wait
    while True:
        check()
        try:
            if any(same_page(shown, url) for shown in chrome_addresses()):
                return True
        except Exception:
            return False
        if time.monotonic() >= end:
            return False
        time.sleep(0.2)


@action("open_site", UNDOABLE, {"site": "site name or address"}, lambda site: f"open {site} in Chrome")
def open_site(site: str) -> Result:
    if site.lower().strip() in ("new tab", "a new tab"):
        open_in_browser(NEW_TAB)
        return Result(True, "Opening a new tab.", {"url": NEW_TAB, "done": "Opened a new tab."})
    url = site_url(site)
    if not url:  # unknown name: let Google find it rather than guess an address
        return web_search(site)
    open_in_browser(url)
    return Result(True, f"Opening {site}.", {"url": url, "done": f"Opened {site}."})


@action("web_search", UNDOABLE, {"query": "what to search for"},
        lambda query: f"Google \"{query}\" in Chrome", for_brain=True)
def web_search(query: str) -> Result:
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    open_in_browser(url)
    return Result(True, f"Searching Google for {query}.", {"url": url, "done": f"Searched Google for {query}."})
