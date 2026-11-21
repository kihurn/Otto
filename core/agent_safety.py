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
                 "slack.exe", "outlook.exe", "olk.exe", "thunderbird.exe", "signal.exe", "claude.exe", "chatgpt.exe"}
MESSAGING_TITLE = re.compile(r"\b(gmail|outlook|whatsapp|messenger|discord|teams|slack|telegram|instagram|"
                             r"linkedin|messages|claude|chatgpt)\b", re.I)
MESSAGE_BOX = re.compile(r"\b(message|chat|reply|comment|post|compose|write to|send to|dm)\b", re.I)
TERMINAL_EXE = {"powershell.exe", "pwsh.exe", "cmd.exe", "windowsterminal.exe", "wt.exe", "conhost.exe"}
DELETE_KEYS = {"delete", "del", "shift+delete", "shift+del", "ctrl+d"}
SELECT_ALL = {"ctrl+a"}
RUN_BUTTONS = re.compile(r"^(run|ok|open|execute)$", re.I)
# An app's own "save changes?" answer that throws work away: always the user's call (11 Nov rule). The close tool
# stops before this; this covers the same message reached another way (Alt+F4, the X button).
DISCARD = re.compile(r"\b(?:don'?t save|do not save|discard(?: changes)?|don'?t keep|close without saving)\b", re.I)


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
    """Where a risky step would land, taken when Otto asks for your yes, including the text in the focused box
    (the draft the question read out), when Windows lets us read it."""
    shot = front(ctx)
    # A terminal's text keeps changing with output; its command is checked by retyping it instead (tools._keys).
    shot["draft"] = None if ctx.dry_run or _is_command(shot) else _draft()
    return shot


def _draft() -> str | None:
    text = focused_text()
    return None if text is None else " ".join(text.split())


def draft_changed(before: dict | None, ctx) -> bool:
    """The box's text is not what it was when Otto asked (Codex review 19 Nov: you could edit the message while the
    question was open, and the yes then sent text Otto never read out). Unreadable at ask time: nothing to compare;
    unreadable now but readable then: counts as changed."""
    if not before or before.get("draft") is None or ctx.dry_run:
        return False
    return _draft() != before["draft"]


def same_place(before: dict | None, ctx) -> bool:
    """After your yes: bring the window from the question back to the front, and check it is still the same
    window with the same box focused. If anything changed, the yes is not used (it was for that place only)."""
    if not before:
        return False
    if ctx.dry_run:
        return front(ctx) == {k: v for k, v in before.items() if k != "draft"}
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
        return _final(args.get("keys", "")) == "enter"
    text = str(args.get("text", "")) if name == "type" else ""
    return "\n" in text.rstrip(" ") or "\r" in text


def blocked(name: str, args: dict, ctx) -> str | None:
    """A send that may not even be offered for a yes yet: the chat must have been read since the last open or
    click, so Otto knows the right chat is open (a click from a screenshot can land on the wrong person).
    Returns what to tell the model, or None."""
    if ctx.confirmed or not sending(name, args):
        return None
    w = front(ctx)
    if name == "type" and (_is_message(w) or _is_command(w)):
        # Typing and sending in one go: the question would read the box before the new text was added (Codex
        # re-review 20 Nov: "Morning" + " Ki" + new line). Type first, then Enter, so the question reads the result.
        return "Not done. Type the text without a new line, then press enter as its own step."
    if _is_command(w):
        # Enter in a terminal runs exactly the command Otto just typed, nothing else (Codex checkpoint C, 20 Nov).
        return None if command_just_typed(ctx) else (
            "Not run. I only run a command I just typed: type the whole command, then press enter.")
    if not _is_message(w) or _search_box(w) or _read_since_moved(ctx):
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
    # Whenever the box can be read and holds something, its own text is what would be sent, so that is what the
    # question reads out, even if it isn't what Otto typed (an edited draft; Codex/advisor review 19 Nov). Only an
    # unreadable or empty box falls back to the typed text.
    if box:
        # A page of other text (focus on the chat history) is not quoted, and neither is the typed text then: the
        # question names no text rather than text that may not be what is sent.
        shown = box if len(box) <= 300 or (typed and " ".join(typed.split()) in box) else ""
    elif typed:
        shown = typed.strip()
    else:
        shown = ""
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
    """The shortcut written one fixed way ("shift+ctrl+enter" -> "ctrl+shift+enter"), as hotkey() presses it."""
    from hands.win import parse_hotkey
    try:
        mods, last = parse_hotkey(value)
        return "+".join((*mods, last))
    except ValueError:
        return "+".join(p for p in str(value).lower().replace(" ", "").split("+") if p)


def _final(value: str) -> str:
    """The key that does the work, whatever is held with it: alt+enter and ctrl+shift+enter still send."""
    return _keys(value).rsplit("+", 1)[-1]


def command_just_typed(ctx) -> str:
    """The command Otto typed as its last step that changed anything (reads in between are fine), or ""."""
    for h in reversed(ctx.history):
        if h.get("tool") in ("read_window", "look", "point"):
            continue
        return str(h["args"].get("text", "")) if h.get("tool") == "type" and h.get("ok") else ""
    return ""


def _last_typed(ctx) -> str:
    for h in reversed(ctx.history):
        if h.get("tool") == "type" and h.get("ok"):
            return str(h["args"].get("text", ""))
    return ""


def _is_message(w: dict) -> bool:
    return (w["exe"].lower() in MESSAGING_EXE or bool(MESSAGING_TITLE.search(w["title"]))
            or bool(MESSAGE_BOX.search(w["focused"])))


# Where Enter after typing only adds a line or runs a search, never sends (Codex checkpoint C2, 20 Nov: Enter after
# typing in Claude went through unasked because Claude wasn't on the messaging list). Everything else asks.
# (Not VS Code: it has a terminal and a chat panel.)
EDITOR_EXE = {"notepad.exe", "wordpad.exe", "winword.exe", "excel.exe", "powerpnt.exe", "onenote.exe",
              "notepad++.exe", "obsidian.exe"}
PASTE_KEYS = {"ctrl+v", "shift+insert", "ctrl+shift+v"}
SEARCH_FIELD = re.compile(r"\b(search|address|find|url|filter|go to)\b", re.I)
CHAT_SEARCH = re.compile(r"(?:search(?: or start a new chat| chats)?|find in (?:this )?chat)",
                         re.I)


def _search_box(w: dict) -> bool:
    return bool(CHAT_SEARCH.fullmatch(w["focused"].strip()))


def _typed_this_turn(ctx) -> bool:
    """Anything that may have put text in a box this turn: any typing (even one whose check failed: the keys went
    out) or a paste."""
    return any(h.get("tool") == "type" or h.get("tool") == "keys" and _keys(h["args"].get("keys", "")) in PASTE_KEYS
               for h in ctx.history)


def _harmless_enter(w: dict) -> bool:
    """Enter here can't send anything: a known editor, or a box Windows names as a search or address field.
    An empty or unreadable name is not known to be harmless."""
    return w["exe"].lower() in EDITOR_EXE or bool(w["focused"] and SEARCH_FIELD.search(w["focused"]))


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
    if ctx.confirmed or name in ("read_window", "find_files", "look_up", "search", "ask_user", "done", "look", "point",
                                 "scroll"):
        return None
    if name == "keys":
        keys, final = _keys(args.get("keys", "")), _final(args.get("keys", ""))
        w = front(ctx)
        if final in ("enter", "space") and w["focused"]:
            # Enter or Space on a focused button presses it: the very same decision as clicking it.
            question = _pressing(w["focused"], w["focused"], ctx, w)
            if question:
                return question
        if final == "enter" and _is_command(w):
            return f'run "{command_just_typed(ctx)}" in {_app_name(w)}'
        if final == "enter" and not _search_box(w) and (
                _is_message(w) or (_typed_this_turn(ctx) and not _harmless_enter(w))):
            return _send_question(ctx, w, _last_typed(ctx))
        if final in {"delete", "backspace"} and _selected_all(ctx):
            return f"delete everything selected in {_app_name(w)}"
        if (keys in DELETE_KEYS or final == "delete") and (w["exe"].lower() == "explorer.exe" or _is_message(w)
                                                          or re.search(r"\b(mail|inbox)\b", w["title"], re.I)):
            return f"delete the selected item in {_app_name(w)}"
        return None
    if name == "type":
        text = str(args.get("text", ""))
        if "\n" in text.rstrip(" ") or "\r" in text:
            w = front(ctx)
            if _is_command(w):
                return f'run "{text.strip()}" in {_app_name(w)}'
            if _is_message(w) or not _harmless_enter(w):       # a typed new line can send, like Enter
                return _send_question(ctx, w, text.strip())
        return None
    if name == "click":
        if args.get("control") is None:
            # A position from a screenshot: ask Windows what is really there.
            from core.tools import to_screen
            if not ctx.look:
                return None                   # the tool itself refuses positions without a look
            label = name_at(*to_screen(ctx, args.get("x", 0), args.get("y", 0)))
            if label is None:
                return "click there (I couldn't check what is under that spot)"
            from hands.apps import RISKY_WORDS
            if not label and RISKY_WORDS.search(ctx.why or ""):
                return f"click there ({ctx.why.strip()})"
            return _pressing(label, label, ctx)
        target = next((c for c in ctx.controls if c.get("id") == args.get("control")), None) or {}
        label = " ".join(str(target.get(k) or "") for k in ("name", "automation_id")).strip()
        return _pressing(label, target.get("name") or label, ctx)
    return None


def point_question(x: int, y: int, ctx) -> str | None:
    """What the mouse would really press at this screen point (Windows says what is there), as a question or None."""
    label = name_at(x, y)
    if label is None:
        return "click there (I couldn't check what is under that spot)"
    return _pressing(label, label, ctx)


def question_now(name: str, args: dict, ctx) -> str | None:
    """The question this call would need right now, even if a yes was already given (to compare with it)."""
    saved, ctx.confirmed = ctx.confirmed, False
    try:
        return check(name, args, ctx)
    finally:
        ctx.confirmed = saved


def _pressing(label: str, shown: str, ctx, w: dict | None = None) -> str | None:
    """Pressing a control, however it is pressed (by number, by screen position, or Enter/Space on it while it has
    the focus): one decision for all three (Codex re-review 20 Nov: they used to differ)."""
    from hands.apps import RISKY_WORDS
    if not label:
        # An unnamed button right after typing may be the send arrow (Codex checkpoint C2).
        w = w or front(ctx)
        if _typed_this_turn(ctx) and _is_message(w):
            return _send_question(ctx, w, _last_typed(ctx))     # in a chat it is most likely the send arrow
        if _typed_this_turn(ctx) and not _harmless_enter(w):
            return "press an unnamed button next to what I typed (it may send it)"
        return None
    if DISCARD.search(label):
        return f'press "{shown}" (unsaved changes would be lost)'
    w = w or front(ctx)
    if RISKY_WORDS.search(label):
        if re.search(r"\bsend\b", label, re.I) and _is_message(w):
            return _send_question(ctx, w, _last_typed(ctx))          # what is sent and where, not just "Send"
        return f'press "{shown}"'
    if RUN_BUTTONS.match(shown.strip()) and _is_command(w):
        command = _last_typed(ctx)
        return f'run "{command}"' if command else f'press "{shown}" to run the command'
    return None
