"""When the agent must ask first (design 5.4). Checked in code before every tool call; Qwen can't skip it.

Otto just does it: opening, reading, looking, searching, scrolling, clicking, typing, navigating, closing.
Otto asks first:
- sending: Enter / Ctrl+Enter / Shift+Enter (or a typed new line) in a message box or a messaging app,
  and Send-type buttons
- buying, paying, ordering, checkout
- running a typed command: Enter, Run or OK in a terminal, the Run box or Explorer's address bar
- select-all followed by Delete or Backspace, anywhere
- the Delete key in File Explorer, mail and chat apps
- buttons whose names are risky (core: hands.apps.RISKY_WORDS)
A "yes" lets exactly the next call through (ToolContext.confirmed). Password, card and code fields are refused
by the tools themselves, even after a yes.
"""
from __future__ import annotations

import re

MESSAGING_EXE = {"discord.exe", "whatsapp.exe", "ms-teams.exe", "teams.exe", "messenger.exe", "telegram.exe",
                 "slack.exe", "outlook.exe", "olk.exe", "thunderbird.exe", "signal.exe"}
MESSAGING_TITLE = re.compile(r"\b(gmail|outlook|whatsapp|messenger|discord|teams|slack|telegram|instagram|"
                             r"linkedin|messages)\b", re.I)
MESSAGE_BOX = re.compile(r"\b(message|chat|reply|comment|post|compose|write to|send to|dm)\b", re.I)
TERMINAL_EXE = {"powershell.exe", "pwsh.exe", "cmd.exe", "windowsterminal.exe", "wt.exe", "conhost.exe"}
SEND_KEYS = {"enter", "ctrl+enter", "shift+enter"}
DELETE_KEYS = {"delete", "del", "shift+delete", "shift+del", "ctrl+d"}
SELECT_ALL = {"ctrl+a"}
RUN_BUTTONS = re.compile(r"^(run|ok|open|execute)$", re.I)


# In a dry run nothing is really open, so the app's name stands in for its program file.
DRY_RUN_EXE = {"file explorer": "explorer.exe", "explorer": "explorer.exe", "files": "explorer.exe",
               "terminal": "windowsterminal.exe", "windows terminal": "windowsterminal.exe",
               "command prompt": "cmd.exe", "cmd": "cmd.exe", "powershell": "powershell.exe",
               "windows powershell": "powershell.exe", "run": "", "word": "winword.exe", "microsoft word": "winword.exe",
               "outlook": "outlook.exe", "teams": "ms-teams.exe", "microsoft teams": "ms-teams.exe",
               "vs code": "code.exe", "visual studio code": "code.exe", "chrome": "chrome.exe", "google chrome": "chrome.exe"}


def front(ctx) -> dict:
    """The window really in front right now and the name of its focused control: {hwnd, exe, title, focused}.
    Always read live, because the agent's actions land on whatever is in front, not on the last window read."""
    if ctx.dry_run:
        # Nothing is really open in a dry run: judge by the app the agent last opened or read.
        app = (ctx.app or "").strip()
        exe = DRY_RUN_EXE.get(app.lower(), app.lower().replace(" ", "") + ".exe" if app else "")
        return {"hwnd": 0, "exe": exe, "title": app, "focused": ""}
    from hands import win
    hwnd = win.foreground()
    info = win.window_info(hwnd) if hwnd else {}
    return {"hwnd": hwnd, "exe": info.get("exe", ""), "title": info.get("title", ""), "focused": focused_name()}


def back_to_user_window(ctx) -> None:
    """You typed your request (or your yes) into Otto's own window, so it is in front. The agent's keys and
    reading must land on the window you were using, so bring that one back first."""
    if ctx.dry_run:
        return
    try:
        from hands import win
        from senses import eyes
        if win.foreground() in win.OTTO_WINDOWS:
            other = eyes.last_other_window()
            if other and other.get("hwnd"):
                win.focus(other["hwnd"])
                import time
                time.sleep(0.3)
    except Exception:
        pass


def otto_in_front(ctx) -> bool:
    """Is Otto's own window (where you type to it) still in front, even after trying to go back to yours?
    Keys, typing and mouse actions must never land there."""
    if ctx.dry_run:
        return False
    try:
        from hands import win
        if win.foreground() not in win.OTTO_WINDOWS:
            return False
        back_to_user_window(ctx)
        return win.foreground() in win.OTTO_WINDOWS
    except Exception:
        return False


def _steady(title: str) -> str:
    """A window title without the parts that change by themselves: unread counts and "new message" dots."""
    return re.sub(r"^\W+", "", re.sub(r"\(\d+\+?\)", "", title or "")).strip()


def snapshot(ctx) -> dict:
    """Where a risky step would land, taken when Otto asks for your yes."""
    return front(ctx)


def same_place(before: dict | None, ctx) -> bool:
    """After your yes: bring the window from the question back to the front, and check it is still the same
    window with the same box focused. If anything changed, the yes is not used (it was for that place only)."""
    if not before:
        return False
    if ctx.dry_run:
        return front(ctx) == before
    try:
        from hands import win
        if before.get("hwnd") and win.foreground() != before["hwnd"]:
            if not win.focus(before["hwnd"]):
                return False
            import time
            time.sleep(0.3)
    except Exception:
        return False
    now = front(ctx)
    keys = ("hwnd", "exe") + (("focused",) if before.get("focused") else ())
    return all(now.get(k) == before.get(k) for k in keys) and _steady(now.get("title")) == _steady(before.get("title"))


def sending(name: str, args: dict) -> bool:
    """Would this call send what is in a box (Enter, or a typed new line)?"""
    if name == "keys":
        return _keys(args.get("keys", "")) in SEND_KEYS
    text = str(args.get("text", "")) if name == "type" else ""
    return "\n" in text.rstrip(" ") or "\r" in text


def blocked(name: str, args: dict, ctx) -> str | None:
    """A send that may not even be offered for a yes yet: the chat must have been read since the last open or
    click, so Otto knows the right chat is open (a click from a screenshot can land on the wrong person).
    Returns what to tell the model, or None."""
    if ctx.confirmed or not sending(name, args):
        return None
    w = front(ctx)
    if _is_command(w) or not _is_message(w) or _read_since_moved(ctx):
        return None
    return ("Not sent. First use read_window (or look) to check that the right chat is open and what the message "
            "box holds, then press enter again without clicking anything in between.")


def _read_since_moved(ctx) -> bool:
    """Was the window read (or looked at) after the last open or click in this request?"""
    for h in reversed(ctx.history):
        if h.get("tool") in ("read_window", "look") and h.get("ok"):
            return True
        if h.get("tool") in ("open", "click"):
            return False
    return False


def _send_question(ctx, w: dict, typed: str) -> str:
    """The question before sending, built from what is really there: the box's own text (it may hold more than
    Otto typed, e.g. text left over from an earlier try) and the window's title (which names the chat in most apps)."""
    box = (None if ctx.dry_run else focused_text()) or ""
    box = " ".join(box.split())
    # The box's own text only when it holds what was typed (focus may be on a pane full of other text).
    if typed and typed.strip() and " ".join(typed.split()) in box:
        shown = box
    elif typed:
        shown = typed.strip()
    else:
        shown = box if len(box) <= 300 else ""
    place = re.sub(r"\(\d+\+?\)\s*", "", w.get("title", "")).strip() or _app_name(w)   # no unread counts
    to = re.search(r"\b(?:message|reply|write) to (.+)$", w.get("focused") or "", re.I)
    if to and to[1].strip().lower() not in place.lower():
        place = f"{place}, to {to[1].strip()}"          # WhatsApp names the person only in its message box
    if len(shown) > 200:
        shown = shown[:200] + "..."
    return f'send "{shown}" in {place}' if shown else f"send the message in {place}"


def focused_text() -> str | None:
    """The text in the focused box right now, or None if Windows can't tell."""
    try:
        from pywinauto.uia_defines import IUIA
        from hands import ui_probe
        return ui_probe.read_text({"element": IUIA().get_focused_element()}, limit=2000)
    except Exception:
        return None


def focused_name() -> str:
    try:
        from pywinauto.uia_defines import IUIA
        return (IUIA().get_focused_element().CurrentName or "").strip()
    except Exception:
        return ""


def name_at(x: int, y: int) -> str | None:
    """The name of whatever is on the screen at this point, from Windows.
    "" = something is there but it has no name; None = Windows could not be asked (treated as risky)."""
    try:
        from pywinauto.uia_defines import IUIA
        import ctypes.wintypes
        element = IUIA().iuia.ElementFromPoint(ctypes.wintypes.POINT(int(x), int(y)))
        return (element.CurrentName or "").strip() if element else ""
    except Exception:
        return None


def _keys(value: str) -> str:
    return "+".join(p for p in str(value).lower().replace(" ", "").split("+") if p)


def _last_typed(ctx) -> str:
    for h in reversed(ctx.history):
        if h.get("tool") == "type" and h.get("ok"):
            return str(h["args"].get("text", ""))
    return ""


def _is_message(w: dict) -> bool:
    return (w["exe"].lower() in MESSAGING_EXE or bool(MESSAGING_TITLE.search(w["title"]))
            or bool(MESSAGE_BOX.search(w["focused"])))


def _is_command(w: dict) -> bool:
    exe, title, focused = w["exe"].lower(), w["title"], w["focused"]
    if exe in TERMINAL_EXE:
        return True
    if title.strip() == "Run":                                      # the Win+R box
        return True
    if exe == "explorer.exe" and re.search(r"\baddress\b", focused, re.I):
        return True
    return exe == "code.exe" and re.search(r"\bterminal\b", focused, re.I) is not None


def _app_name(w: dict) -> str:
    title = w["title"].split(" - ")[-1].strip() if w["title"] else ""
    return title or w["exe"].removesuffix(".exe") or "this app"


def _selected_all(ctx) -> bool:
    """Was select-all the last thing done (nothing but reading since)?"""
    for h in reversed(ctx.history):
        if h.get("tool") in ("read_window", "look", "point"):
            continue
        if h.get("tool") == "keys" and _keys(h["args"].get("keys", "")) in SELECT_ALL:
            return True
        if h.get("tool") == "click" and re.search(r"select all", str(h.get("name", "")), re.I):
            return True
        return False
    return False


def check(name: str, args: dict, ctx) -> str | None:
    """None = go ahead. Otherwise the question to ask (the call waits for a yes)."""
    if ctx.confirmed or name in ("read_window", "find_files", "look_up", "google", "ask_user", "done", "look", "point",
                                 "scroll"):
        return None
    if name == "keys":
        keys = _keys(args.get("keys", ""))
        w = front(ctx)
        if keys in SEND_KEYS and _is_command(w):
            command = _last_typed(ctx)
            return f'run "{command}" in {_app_name(w)}' if command else f"press {keys} to run the command in {_app_name(w)}"
        if keys in SEND_KEYS and _is_message(w):
            return _send_question(ctx, w, _last_typed(ctx))
        if keys in {"delete", "del", "backspace"} and _selected_all(ctx):
            return f"delete everything selected in {_app_name(w)}"
        if keys in DELETE_KEYS and (w["exe"].lower() == "explorer.exe" or _is_message(w)
                                    or re.search(r"\b(mail|inbox)\b", w["title"], re.I)):
            return f"delete the selected item in {_app_name(w)}"
        if keys in SEND_KEYS | {"space"}:
            # Enter or Space on a focused button presses it: same rule as clicking it.
            from hands.apps import RISKY_WORDS
            if w["focused"] and RISKY_WORDS.search(w["focused"]):
                return f'press "{w["focused"]}"'
        return None
    if name == "type":
        text = str(args.get("text", ""))
        if "\n" in text.rstrip(" ") or "\r" in text:
            w = front(ctx)
            if _is_message(w):
                return _send_question(ctx, w, text.strip())
            if _is_command(w):
                return f'run "{text.strip()}" in {_app_name(w)}'
        return None
    if name == "click" and args.get("control") is None:
        # A position from a screenshot: ask Windows what is really there.
        from core.tools import to_screen
        from hands.apps import RISKY_WORDS
        if not ctx.look:
            return None                       # the tool itself refuses positions without a look
        label = name_at(*to_screen(ctx, args.get("x", 0), args.get("y", 0)))
        if label is None:
            return "click there (I couldn't check what is under that spot)"
        if label and RISKY_WORDS.search(label):
            w = front(ctx)
            if re.search(r"\bsend\b", label, re.I) and _is_message(w):
                return _send_question(ctx, w, _last_typed(ctx))
            return f'press "{label}"'
        if not label and RISKY_WORDS.search(ctx.why or ""):
            return f"click there ({ctx.why.strip()})"
        return None
    if name == "click":
        from hands.apps import RISKY_WORDS
        target = next((c for c in ctx.controls if c.get("id") == args.get("control")), None)
        label = " ".join(str((target or {}).get(k) or "") for k in ("name", "automation_id")).strip()
        if label and RISKY_WORDS.search(label):
            w = front(ctx)
            if re.search(r"\bsend\b", label, re.I) and _is_message(w):
                return _send_question(ctx, w, _last_typed(ctx))      # what is sent and where, not just "Send"
            return f'press "{(target or {}).get("name") or label}"'
        if label and RUN_BUTTONS.match((target or {}).get("name", "").strip()):
            w = front(ctx)
            if _is_command(w):
                command = _last_typed(ctx)
                return f'run "{command}"' if command else f'press "{target["name"]}" to run the command'
        return None
    return None
