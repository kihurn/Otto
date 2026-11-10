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


@action("open_site", UNDOABLE, {"site": "site name or address"}, lambda site: f"open {site} in Chrome")
def open_site(site: str) -> Result:
    url = site_url(site)
    if not url:  # unknown name: let Google find it rather than guess an address
        return web_search(site)
    open_in_browser(url)
    return Result(True, f"Opening {site}.")


@action("web_search", UNDOABLE, {"query": "what to search for"},
        lambda query: f"Google \"{query}\" in Chrome", for_brain=True)
def web_search(query: str) -> Result:
    open_in_browser("https://www.google.com/search?q=" + urllib.parse.quote(query))
    return Result(True, f"Searching Google for {query}.")
