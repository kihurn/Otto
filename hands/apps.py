"""Apps: the list of what's installed, plus open / switch / minimise / close / search / click."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.parse

from core.config import ALIASES_FILE, APPS_CACHE, DEFAULTS, load_json, save_json
from hands import win
from hands.registry import ASK, READ, UNDOABLE, Result, action

# Windows tools that aren't always in the Start menu list
BUILTIN = {
    "File Explorer": ["explorer.exe"],
    "Task Manager": ["taskmgr.exe"],
    "Notepad": ["notepad.exe"],
    "Calculator": ["calc.exe"],
    "Settings": ["explorer.exe", "ms-settings:"],
    "Command Prompt": ["cmd.exe"],
    "Control Panel": ["control.exe"],
}

# Apps whose search can be opened directly with a link (most reliable way)
SEARCH_LINKS = {
    "spotify": "spotify:search:{q}",
    "steam": "steam://openurl/https://store.steampowered.com/search/?term={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "netflix": "https://www.netflix.com/search?q={q}",
    "settings": "ms-settings:search?query={q}",
}

_SKIP = re.compile(r"uninstall|readme|read me|help|documentation|website|release notes|license|"
                   r"what's new|manual|\.url$|\.chm$|\.txt$|\.pdf$|repair|support", re.I)


class AppIndex:
    """Installed apps from the Start menu (Get-StartApps), refreshed in the background."""

    def __init__(self):
        self.apps: list[dict] = load_json(APPS_CACHE, {}).get("apps", [])
        aliases = load_json(ALIASES_FILE, None) or load_json(DEFAULTS / "app_aliases.json", {})
        self.aliases: dict[str, str] = {k.lower(): v for k, v in aliases.items()}
        self.updated = load_json(APPS_CACHE, {}).get("updated", 0)
        self._lock = threading.Lock()
        for name in BUILTIN:
            if not any(a["name"] == name for a in self.apps):
                self.apps.append({"name": name, "id": None})

    def refresh(self) -> int:
        if not win.IS_WINDOWS:
            return len(self.apps)
        cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
               "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True,
                                 text=True, encoding="utf-8", timeout=60).stdout
            items = json.loads(out or "[]")
            if isinstance(items, dict):
                items = [items]
        except Exception:
            return len(self.apps)
        apps = [{"name": i["Name"], "id": i["AppID"]} for i in items
                if i.get("Name") and i.get("AppID") and not _SKIP.search(i["Name"])]
        names = {a["name"] for a in apps}
        apps += [{"name": n, "id": None} for n in BUILTIN if n not in names]
        with self._lock:
            self.apps = apps
            self.updated = time.time()
        save_json(APPS_CACHE, {"updated": self.updated, "apps": apps})
        return len(apps)

    def refresh_in_background(self, max_age_s: int = 3600) -> None:
        if time.time() - self.updated > max_age_s or len(self.apps) <= len(BUILTIN):
            threading.Thread(target=self.refresh, daemon=True).start()

    def names(self) -> list[str]:
        return [a["name"] for a in self.apps]

    def known_words(self) -> set[str]:
        words = set()
        for n in self.names() + list(self.aliases):
            words.update(w for w in re.findall(r"[a-z0-9]+", n.lower()) if len(w) > 2)
        return words

    def get(self, name: str) -> dict | None:
        return next((a for a in self.apps if a["name"] == name), None)

    def match_exact(self, spoken: str) -> dict | None:
        """Resolve a complete installed name or explicit alias, without fuzzy matching."""
        name = " ".join(spoken.lower().split())
        target = self.aliases.get(name, name).lower()
        return next((a for a in self.apps if a["name"].lower() == target), None)

    def match(self, spoken: str) -> tuple[dict | None, int, list[str]]:
        """Best app for a spoken name: (app, score 0-100, other close names)."""
        from rapidfuzz import fuzz, process

        s = spoken.lower().strip()
        if not s:
            return None, 0, []
        if s in self.aliases:
            app = self.get(self.aliases[s]) or self._loose(self.aliases[s])
            if app:
                return app, 100, []
        exact = [a for a in self.apps if a["name"].lower() == s]
        if exact:
            return exact[0], 100, []
        choices = {a["name"]: a["name"].lower() for a in self.apps}
        found = process.extract(s, choices, scorer=fuzz.WRatio, limit=3)
        if not found:
            return None, 0, []
        (_, score, name), others = found[0], [f[2] for f in found[1:] if f[1] >= 75]
        # short spoken names ("obs") must match the start of a word, not the middle
        if len(s) <= 3 and not re.search(rf"\b{re.escape(s)}", name.lower()):
            score = min(score, 60)
        return self.get(name), int(score), others

    def _loose(self, name: str) -> dict | None:
        app, score, _ = self.match_plain(name)
        return app if score >= 85 else None

    def match_plain(self, name: str):
        from rapidfuzz import fuzz, process
        choices = {a["name"]: a["name"].lower() for a in self.apps}
        found = process.extractOne(name.lower(), choices, scorer=fuzz.WRatio)
        return (self.get(found[2]), int(found[1]), []) if found else (None, 0, [])

    def find_in_text(self, text: str) -> tuple[str | None, int]:
        """Look for an app name anywhere in a sentence. Returns (spoken words, score)."""
        from rapidfuzz import fuzz

        words = re.findall(r"[a-z0-9.+#']+", text.lower())
        stop = {"open", "launch", "start", "close", "quit", "switch", "to", "the", "a", "an", "up", "app",
                "please", "can", "you", "could", "on", "in", "and", "search", "for", "me", "my", "fire",
                "bring", "go", "back", "over", "pull", "minimise", "minimize", "click", "button", "of",
                "play", "find", "look", "with", "this", "that", "it", "is", "window", "exit", "kill", "run",
                "hey", "otto", "auto", "lets", "let's", "now", "pls", "plz", "just", "into", "inside", "type"}
        best, best_score = None, 0
        candidates = [a["name"].lower() for a in self.apps] + list(self.aliases)
        for n in range(4, 0, -1):
            for i in range(len(words) - n + 1):
                gram = words[i:i + n]
                if gram[0] in stop or gram[-1] in stop:
                    continue
                phrase = " ".join(gram)
                for c in candidates:
                    score = fuzz.ratio(phrase, c)
                    if len(phrase) >= 4 and (c.startswith(phrase + " ") or c == phrase):
                        score = max(score, 92)
                    elif len(phrase) >= 4 and re.search(rf"\b{re.escape(phrase)}\b", c):
                        score = max(score, 90)
                    if score > best_score:
                        best, best_score = phrase, score
        return (best, best_score) if best_score >= 70 else (None, 0)


INDEX = AppIndex()


def _launch(app: dict) -> None:
    if app["name"] in BUILTIN and not app.get("id"):
        subprocess.Popen(BUILTIN[app["name"]])
    else:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['id']}"])


def _resolve(app: str) -> tuple[dict | None, Result | None]:
    found, score, _ = INDEX.match(app)
    if not found or score < 75:
        return None, Result(False, f"{app.title()} isn't installed, as far as I can see.")
    return found, None


@action("open_app", UNDOABLE, {"app": "app name"}, lambda app: f"open {app}", for_brain=True)
def open_app(app: str) -> Result:
    found, err = _resolve(app)
    if err:
        return err
    name = found["name"]
    already = win.find_window(name) if win.IS_WINDOWS else None
    if already:
        win.focus(already["hwnd"])
        return Result(True, f"{name} is already open, so I brought it to the front.", {"app": name})
    _launch(found)
    if not win.IS_WINDOWS:
        return Result(True, f"Opening {name}.", {"app": name})
    for _ in range(24):                      # check for its window for up to ~6 seconds
        time.sleep(0.25)
        window = win.find_window(name)
        if window:
            win.focus(window['hwnd'])
            return Result(True, f"Opened {name}.", {"app": name})
    return Result(True, f"I asked Windows to open {name}; it's still loading.", {"app": name})


@action("switch_to", UNDOABLE, {"app": "app name"}, lambda app: f"switch to {app}", for_brain=True)
def switch_to(app: str) -> Result:
    w = win.find_window(app)
    if w and win.focus(w["hwnd"]):
        return Result(True, f"Switched to {app.title()}.")
    res = open_app(app)
    if res.ok:
        res.say = f"{app.title()} wasn't open, so I'm opening it."
    return res


@action("minimise", UNDOABLE, {"app": "app name, or empty for the current window"},
        lambda app="": f"minimise {app or 'this window'}")
def minimise(app: str = "") -> Result:
    from senses import eyes
    w = win.find_window(app) if app else eyes.last_other_window()
    if not w:
        return Result(False, f"I can't find a {app or 'window'} to minimise.")
    win.minimise(w["hwnd"])
    return Result(True, f"Minimised {app.title() if app else w['title'][:40]}.")


@action("close_app", ASK, {"app": "app name"}, lambda app: f"close {app} (unsaved work in it could be lost)")
def close_app(app: str) -> Result:
    w = win.find_window(app)
    if not w:
        return Result(False, f"{app.title()} doesn't seem to be open.")
    win.close(w["hwnd"])
    return Result(True, f"Closing {app.title()}.")


def builtin_search_link(app: str, query: str) -> str | None:
    key = app.lower().strip()
    found, score, _ = INDEX.match(app)
    if found and score >= 75:
        key = found["name"].lower()
    for name, link in SEARCH_LINKS.items():
        if name in key:
            # A protocol URI must not contain raw spaces: Windows may truncate it.
            # quote (not quote_plus) keeps spaces distinct from literal plus signs.
            q = urllib.parse.quote(query, safe='')
            return link.format(q=q)
    return None


@action("search_in_app", UNDOABLE, {"app": "app name", "query": "what to search for"},
        lambda app, query: f"search {app} for \"{query}\"")
def search_in_app(app: str, query: str) -> Result:
    if app.casefold().strip() == 'spotify' and win.IS_WINDOWS:
        opened = open_app('Spotify')
        window = win.find_window('Spotify')
        if not opened.ok or not window or not win.focus(window['hwnd']):
            return Result(False, 'I could not focus Spotify search.')
        from hands.spotify_search import search
        return search(window['hwnd'], query)
    link = builtin_search_link(app, query)
    if not link:
        return Result(False, "no_method", {"needs_plan": True})
    if link.startswith("http"):
        from hands.web import open_in_browser
        open_in_browser(link)
    else:
        os.startfile(link)
    return Result(True, f"Searching {app.title()} for {query}.")


@action("open_link", UNDOABLE, {"uri": "a web address or app link, e.g. spotify:search:lofi"},
        lambda uri: f"open {uri}", for_brain=True)
def open_link(uri: str) -> Result:
    if uri.startswith(("http://", "https://")):
        from hands.web import open_in_browser
        open_in_browser(uri)
    else:
        os.startfile(uri)
    return Result(True, "Done.")


RISKY_WORDS = re.compile(r"\b(send|buy|pay|purchase|order|submit|post|delete|remove|uninstall|"
                         r"confirm|transfer|checkout|publish|sign out|log out|reset|format)\b", re.I)


@action("click_button", UNDOABLE, {"app": "app name", "button": "the button's name as shown"},
        lambda app, button: f"click \"{button}\" in {app}", for_brain=True,
        note="buttons named send/buy/pay/delete always need the user's yes")
def click_button(app: str, button: str):
    """Press a named button, tab, link or menu item, and confirm the window reacted (hands/app_control.py)."""
    from hands.app_control import click_named
    return click_named(app, button)


@action("hotkey", UNDOABLE, {"keys": "e.g. ctrl+l, ctrl+t, enter"}, lambda keys: f"press {keys}",
        for_brain=True, note="goes to the window in front; use switch_to or open_app first")
def hotkey(keys: str) -> Result:
    win.hotkey(keys)
    return Result(True, "Done.")


@action("type_text", UNDOABLE, {"text": "text to type"}, lambda text: f"type \"{text[:40]}\"",
        for_brain=True, note="types into the window in front; never into password boxes")
def type_text(text: str) -> Result:
    if win.focused_is_password():
        return Result(False, "That's a password box, and I never type into those.")
    win.type_text(text)
    return Result(True, "Typed it.")


@action("wait", READ, {"seconds": "0.2 to 5"}, lambda seconds: f"wait {seconds}s", for_brain=True,
        note="give an app time to open before typing or clicking")
def wait(seconds) -> Result:
    time.sleep(max(0.1, min(5.0, float(seconds))))
    return Result(True, "")
