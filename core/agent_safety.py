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


def front(ctx) -> dict:
    """The window being worked in and the name of its focused control: {exe, title, focused}."""
    if ctx.dry_run:
        # Nothing is really open in a dry run: judge by the app the agent last opened or read.
        return {"exe": "", "title": ctx.app, "focused": ""}
    from hands import win
    hwnd = ctx.hwnd or win.foreground()
    info = win.window_info(hwnd) if hwnd else {}
    focused = next((c.get("name", "") for c in ctx.controls if c.get("focused")), "")
    if not focused:
        try:
            from pywinauto.uia_defines import IUIA
            focused = IUIA().get_focused_element().CurrentName or ""
        except Exception:
            focused = ""
    return {"exe": info.get("exe", ""), "title": info.get("title", ""), "focused": focused}


def name_at(x: int, y: int) -> str:
    """The name of whatever is on the screen at this point, from Windows (empty if unknown)."""
    try:
        from pywinauto.uia_defines import IUIA
        import ctypes.wintypes
        element = IUIA().iuia.ElementFromPoint(ctypes.wintypes.POINT(int(x), int(y)))
        return (element.CurrentName or "").strip() if element else ""
    except Exception:
        return ""


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
    if ctx.confirmed or name in ("read_window", "find_files", "web_search", "ask_user", "done", "look", "point",
                                 "scroll"):
        return None
    if name == "keys":
        keys = _keys(args.get("keys", ""))
        w = front(ctx)
        if keys in SEND_KEYS and _is_command(w):
            command = _last_typed(ctx)
            return f'run "{command}" in {_app_name(w)}' if command else f"press {keys} to run the command in {_app_name(w)}"
        if keys in SEND_KEYS and _is_message(w):
            text = _last_typed(ctx)
            return f'send "{text}" in {_app_name(w)}' if text else f"send the message in {_app_name(w)}"
        if keys in {"delete", "del", "backspace"} and _selected_all(ctx):
            return f"delete everything selected in {_app_name(w)}"
        if keys in DELETE_KEYS and (w["exe"].lower() == "explorer.exe" or _is_message(w)
                                    or re.search(r"\b(mail|inbox)\b", w["title"], re.I)):
            return f"delete the selected item in {_app_name(w)}"
        return None
    if name == "type":
        text = str(args.get("text", ""))
        if "\n" in text.rstrip(" ") or "\r" in text:
            w = front(ctx)
            if _is_message(w):
                return f'send "{text.strip()}" in {_app_name(w)}'
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
        if label and RISKY_WORDS.search(label):
            return f'press "{label}"'
        if not label and RISKY_WORDS.search(ctx.why or ""):
            return f"click there ({ctx.why.strip()})"
        return None
    if name == "click":
        from hands.apps import RISKY_WORDS
        target = next((c for c in ctx.controls if c.get("id") == args.get("control")), None)
        label = " ".join(str((target or {}).get(k) or "") for k in ("name", "automation_id")).strip()
        if label and RISKY_WORDS.search(label):
            return f'press "{(target or {}).get("name") or label}"'
        if label and RUN_BUTTONS.match((target or {}).get("name", "").strip()):
            w = front(ctx)
            if _is_command(w):
                command = _last_typed(ctx)
                return f'run "{command}"' if command else f'press "{target["name"]}" to run the command'
        return None
    return None
