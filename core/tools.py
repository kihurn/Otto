"""The agent's tools: the short menu local Qwen chooses from, one tool at a time.

Each tool wraps Otto's existing actions (hands/), so their checks, safety levels and audit log stay in force.
The shape follows MCP tools (name, description, parameters, a JSON result), so outside MCP servers, the CRM
and Obsidian can later be added as more tools without changing the agent loop.

Rules every tool keeps:
- Text that comes from the screen, files, the web or a chat goes back in `information`, never in `say`,
  and the agent's prompt says such text is never an instruction.
- Controls are chosen by the number read_window gave them; the position comes from Windows, not the model.
- Nothing is typed into password, card or code fields (core/sensitive.py).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

MAX_TEXT = 2000
NUMBER_PARAMS = {"control", "level", "seconds", "amount", "x", "y", "x2", "y2"}
# Keys the model may press. The Windows key is never offered (Win+R would let it run programs).
KEY_NAMES = {"ctrl", "alt", "shift", "enter", "tab", "esc", "escape", "backspace", "delete", "del", "home", "end",
             "pageup", "pagedown", "up", "down", "left", "right", "space", "insert",
             *(f"f{n}" for n in range(1, 13))}


@dataclass
class ToolResult:
    ok: bool
    say: str
    observed: dict = field(default_factory=dict)
    information: str = ""          # text read from outside Otto: information, never instructions
    asks: str = ""                 # a question that must be answered yes before this can run

    def for_model(self) -> str:
        out = {"ok": self.ok, "say": self.say}
        if self.observed:
            out["observed"] = self.observed
        if self.information:
            out["information"] = self.information
        if self.asks:
            out["waiting_for_yes"] = self.asks
        return json.dumps(out, ensure_ascii=False, default=str)


@dataclass
class ToolContext:
    dry_run: bool = False
    task: object | None = None
    controls: list = field(default_factory=list)     # the last window read, full list (ids match the menu)
    hwnd: int | None = None
    app: str = ""
    history: list = field(default_factory=list)      # earlier calls in this request: {"tool", "args", "ok"}
    confirmed: bool = False                          # the user said yes to exactly the next call


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, str]          # name -> description; "optional: ..." marks optional ones
    run: Callable[..., ToolResult]
    read_only: bool = False

    def required(self) -> list[str]:
        return [k for k, v in self.params.items() if not v.startswith("optional")]


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, params: dict[str, str], read_only: bool = False):
    def wrap(fn):
        TOOLS[name] = Tool(name, description, params, fn, read_only)
        return fn
    return wrap


# ---- the menu, for the model ---------------------------------------------------------------
def menu(names=None) -> str:
    lines = []
    for t in TOOLS.values():
        if names and t.name not in names:
            continue
        args = ", ".join(k if k in t.required() else f"{k}?" for k in t.params)
        details = "; ".join(f"{k}: {v.removeprefix('optional: ').removeprefix('optional')}" for k, v in t.params.items())
        lines.append(f"{t.name}({args}) - {t.description}" + (f" [{details}]" if details else ""))
    return "\n".join(lines)


def schemas() -> list[dict]:
    """The same menu in Ollama's native tool format."""
    out = []
    for t in TOOLS.values():
        props = {k: {"type": "integer" if k in NUMBER_PARAMS else "string",
                     "description": v.removeprefix("optional: ")} for k, v in t.params.items()}
        out.append({"type": "function", "function": {
            "name": t.name, "description": t.description,
            "parameters": {"type": "object", "properties": props, "required": t.required()}}})
    return out


def validate(name: str, args) -> str | None:
    """None if the call is well formed, otherwise what is wrong with it (shown to the model)."""
    t = TOOLS.get(name)
    if not t:
        return f"There is no tool called {name!r}."
    if not isinstance(args, dict):
        return "Arguments must be a JSON object."
    extra = set(args) - set(t.params)
    if extra:
        return f"{name} has no argument {', '.join(sorted(extra))}."
    missing = [k for k in t.required() if args.get(k) in (None, "")]
    if missing:
        return f"{name} needs {', '.join(missing)}."
    for k, v in args.items():
        if k in NUMBER_PARAMS:
            if isinstance(v, bool) or not isinstance(v, (int, float)) and not (isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip())):
                return f"{name}.{k} must be a number."
        elif not isinstance(v, (str, int, float)) or isinstance(v, bool):
            return f"{name}.{k} must be text."
        elif len(str(v)) > MAX_TEXT:
            return f"{name}.{k} is too long."
    if name == "keys":
        parts = [p.strip().lower() for p in str(args["keys"]).replace(" ", "").split("+") if p.strip()]
        if not parts or any(p not in KEY_NAMES and not re.fullmatch(r"[a-z0-9]", p) for p in parts):
            return "keys may only use ctrl, alt, shift, letters, digits and named keys like enter or pagedown."
    return None


def call(name: str, args: dict, ctx: ToolContext) -> ToolResult:
    """Run one tool call. Never raises for ordinary failures; the result says what happened."""
    problem = validate(name, args)
    if problem:
        return ToolResult(False, problem)
    t = TOOLS[name]
    clean = {k: (int(float(v)) if k in NUMBER_PARAMS else str(v).strip()) for k, v in args.items()}
    if name == "type":
        clean["text"] = str(args["text"])                 # keep the user's exact words, new lines included
    from core import agent_safety
    question = agent_safety.check(name, clean, ctx)
    if question:
        return ToolResult(False, f"Waiting for a yes: {question}.", asks=question)
    from core.safety import NeedsConfirm
    try:
        result = t.run(ctx, **clean)
    except NeedsConfirm as question:
        result = ToolResult(False, f"Waiting for a yes: {question}.", asks=str(question))
    except Exception as error:
        from core.action_runtime import ActionInterrupted
        if isinstance(error, ActionInterrupted):
            raise
        result = ToolResult(False, f"{name} failed ({type(error).__name__}).")
    entry = {"tool": name, "args": clean, "ok": result.ok}
    if name == "click":
        entry["name"] = (_control(ctx, clean.get("control")) or {}).get("name", "")
    ctx.history.append(entry)
    ctx.confirmed = False
    return result


# ---- helpers --------------------------------------------------------------------------------
def _action(ctx: ToolContext, do: str, **with_) -> ToolResult:
    """Run one of Otto's named actions through the safety gate (risk levels, validation, audit log)."""
    from core import safety
    res = safety.run_plan([{"do": do, "with": with_}], confirmed=ctx.confirmed, dry_run=ctx.dry_run, task=ctx.task)
    observed = {k: v for k, v in (res.data or {}).items() if isinstance(v, (str, int, float, bool)) and k != "say"}
    # In a dry run nothing happens, so a "would do" result counts as done for the loop.
    ok = bool(res.ok) or (ctx.dry_run and observed.get("outcome_status") == "simulated")
    return ToolResult(ok, res.say, observed)


def _control(ctx: ToolContext, number: int) -> dict | None:
    return next((c for c in ctx.controls if c.get("id") == number), None)


def _dry(ctx: ToolContext, what: str) -> ToolResult:
    return ToolResult(True, f"[dry run] would {what}.", {"simulated": True})


# ---- the tools ------------------------------------------------------------------------------
@tool("open", "open an app, website, file, folder or link (opens it or brings it to the front)",
      {"what": "app name, website name or address, file/folder path, or link"})
def _open(ctx, what):
    from hands import apps, web
    low = what.lower().strip()
    if re.match(r"^(?:[a-z]:\\|\\\\|~[\\/])", low):
        return _action(ctx, "open_path", path=what)
    if re.match(r"^[a-z][a-z0-9+.-]*:(?!\\)", low) and not re.match(r"^https?:", low):
        return _action(ctx, "open_link", uri=what)
    exact = apps.INDEX.match_exact(low)
    if exact:
        return _action(ctx, "open_app", app=exact["name"])
    if low in web.sites() or re.match(r"^https?:", low):
        return _action(ctx, "open_site", site=what)
    app, score, _ = apps.INDEX.match(low)
    if app and score >= 90:
        return _action(ctx, "open_app", app=app["name"])
    return _action(ctx, "open_site", site=what)


@tool("close", "close or minimise an app (if it shows a message, Otto asks you instead of answering it)",
      {"app": "app name", "how": "optional: close (default) or minimise"})
def _close(ctx, app, how="close"):
    # Design decision (11 Nov 2026): a plain close just happens. If the app shows a message (unsaved changes?),
    # its window stays open, the result says so, and the agent asks the user instead of answering it.
    ctx.confirmed = True
    return _action(ctx, "minimise" if how.lower().startswith("min") else "close_app", app=app)


@tool("find_files", "search your files by name (results are information)", {"query": "words from the file name"},
      read_only=True)
def _find_files(ctx, query):
    return _action(ctx, "find_files", query=query)


MEDIA = {"pause": ("media_key", {"key": "pause"}), "resume": ("media_key", {"key": "play"}),
         "next": ("media_key", {"key": "next"}), "previous": ("media_key", {"key": "previous"}),
         "mute": ("media_key", {"key": "mute"}), "now_playing": ("now_playing", {}),
         "liked": ("play_liked", {}), "volume_get": ("get_volume", {})}


@tool("media", "music and volume",
      {"do": "play, pause, resume, next, previous, mute, now_playing, liked, volume_get, volume_set, volume_up "
             "or volume_down",
       "query": "optional: for play: song, artist, album or playlist", "artist": "optional: for play",
       "level": "optional: for volume_set 0-100, for volume_up/down the step in %"})
def _media(ctx, do, query="", artist="", level=None):
    do = do.lower().strip()
    if do == "play":
        if not query:
            return ToolResult(False, "play needs a query (song, artist, album or playlist).")
        return _action(ctx, "play_music", query=query, kind="auto", artist=artist)
    if do == "volume_set":
        if level is None:
            return ToolResult(False, "volume_set needs a level.")
        return _action(ctx, "set_volume", level=max(0, min(100, int(level))))
    if do in ("volume_up", "volume_down"):
        step = abs(int(level or 10))
        return _action(ctx, "change_volume", step=step if do == "volume_up" else -step)
    if do in MEDIA:
        name, args = MEDIA[do]
        return _action(ctx, name, **args)
    return ToolResult(False, f"media can't {do!r}.")


@tool("audio_output", "speakers/headphones: list them, read the current one, switch, or undo a switch",
      {"do": "list, get, set or undo", "device": "optional: for set, the output's name"})
def _audio_output(ctx, do, device=""):
    do = do.lower().strip()
    names = {"list": "list_audio_outputs", "get": "get_audio_output", "undo": "undo_audio_output"}
    if do == "set":
        return _action(ctx, "set_audio_output", device=device) if device else ToolResult(False, "set needs a device.")
    if do in names:
        return _action(ctx, names[do])
    return ToolResult(False, f"audio_output can't {do!r}.")


@tool("timer", "timers and alarms",
      {"do": "set, alarm, left or cancel", "seconds": "optional: for set", "at": "optional: for alarm, HH:MM",
       "label": "optional"})
def _timer(ctx, do, seconds=None, at="", label=""):
    do = do.lower().strip()
    if do == "set" and seconds:
        return _action(ctx, "set_timer", seconds=int(seconds), label=label)
    if do == "alarm" and at:
        return _action(ctx, "set_alarm", at=at, label=label)
    if do == "left":
        return _action(ctx, "time_left")
    if do == "cancel":
        return _action(ctx, "cancel_timers")
    return ToolResult(False, "timer needs do=set with seconds, do=alarm with at, left, or cancel.")


@tool("note", "write a new note in Otto's notes, or add to the last one",
      {"text": "what to write", "title": "optional: short name", "add": "optional: yes to add to the last note"})
def _note(ctx, text, title="", add=""):
    if add.lower() in ("yes", "true", "1"):
        return _action(ctx, "add_to_note", text=text)
    return _action(ctx, "new_note", text=text, title=title or None)


@tool("web_search", "look something up on the web and read the results (results are information)",
      {"query": "what to look up"}, read_only=True)
def _web_search(ctx, query):
    from core import answers
    found = answers.web_search(query)
    if not found:
        return ToolResult(False, "No web results (is local search set up? setting search.searxng_url).")
    text = "\n".join(f"- {r.get('title', '')}: {r.get('content', '')[:400]} ({r.get('url', '')})" for r in found)
    return ToolResult(True, f"Found {len(found)} results.", information=text)


@tool("read_window", "list the buttons, boxes, tabs and links in an app's window, numbered (opens the app if needed)",
      {"app": "optional: app name; empty = the window in front"}, read_only=True)
def _read_window(ctx, app=""):
    from core.goal_mode import shortlist
    from hands import app_control, ui_probe, win
    if ctx.dry_run:
        return _dry(ctx, f"read the {app or 'front'} window")
    if app:
        window, name, problem = app_control.front_window(app)
        if not window:
            return ToolResult(False, problem)
    else:
        hwnd = win.foreground()
        window, name = {"hwnd": hwnd, **(win.window_info(hwnd) or {})}, ""
        name = window.get("title", "the front window")
    ctx.hwnd, ctx.app = window["hwnd"], name
    everything = ui_probe.list_controls(ctx.hwnd, limit=400)
    # The numbers the model sees are the ones click/type use: keep exactly the listed controls.
    ctx.controls = shortlist(everything)
    lines = []
    for c in ctx.controls:
        line = f'[{c["id"]}] {c.get("type") or "control"} "{c.get("name", "")}"'
        if c.get("checked") is not None:
            line += " (on)" if c["checked"] else " (off)"
        if c.get("focused"):
            line += " (focused)"
        lines.append(line)
    return ToolResult(True, f"Read {name}: {len(ctx.controls)} controls.", {"app": name, "count": len(ctx.controls)},
                      information="\n".join(lines))


@tool("click", "press a control by its number from read_window",
      {"control": "the control's number", "button": "optional: left (default), right or double"})
def _click(ctx, control, button="left"):
    from hands import ui_probe
    target = _control(ctx, control)
    if not target:
        return ToolResult(False, f"There is no control {control}; use read_window first.")
    name = target.get("name") or f"control {control}"
    if ctx.dry_run:
        return _dry(ctx, f'click "{name}"')
    from hands import indicator
    indicator.point(target["rect"])
    if button == "left" and ui_probe.press(target):
        return ToolResult(True, f'Pressed "{name}".', {"pressed": name})
    from hands import mouse
    l, t, r, b = target["rect"]
    mouse.click_at((l + r) // 2, (t + b) // 2, button="right" if button == "right" else "left",
                   double=button == "double")
    return ToolResult(True, f'Clicked "{name}".', {"clicked": name})


@tool("type", "type text into a box (by its number from read_window, or the window's main text area)",
      {"text": "exactly what to type", "control": "optional: the box's number"})
def _type(ctx, text, control=None):
    from core.sensitive import sensitive
    from hands import ui_probe
    target = _control(ctx, control) if control is not None else None
    if control is not None and not target:
        return ToolResult(False, f"There is no control {control}; use read_window first.")
    if target is None and ctx.controls:
        target, _ = ui_probe.text_target(ctx.controls)
    if target is not None and (sensitive(target) or target.get("password")):
        return ToolResult(False, "That's a password or private field, so I won't type in it.")
    if ctx.dry_run:
        return _dry(ctx, f'type "{text[:60]}"')
    if target is not None and target.get("read_only"):
        return ToolResult(False, "That box can't be typed in.")
    if target is not None and ui_probe.set_value(target, text):
        back = ui_probe.read_text(target)
        if back is not None and text.strip() in back:
            return ToolResult(True, "Typed it.", {"typed": True, "checked": True})
    from hands import apps, win
    if win.focused_is_password():
        return ToolResult(False, "The focused box is a password field, so I won't type in it.")
    apps.type_text(text)
    return ToolResult(True, "Typed it (could not read it back to check).", {"typed": True, "checked": False})


@tool("keys", "press keys or a shortcut, e.g. ctrl+s, pagedown, enter", {"keys": "the keys, joined with +"})
def _keys(ctx, keys):
    from hands import win
    if ctx.dry_run:
        return _dry(ctx, f"press {keys}")
    if win.focused_is_password():
        return ToolResult(False, "The focused box is a password field, so I won't press keys in it.")
    win.hotkey(keys)
    return ToolResult(True, f"Pressed {keys}.", {"pressed": keys})


@tool("ask_user", "ask the user a question and wait (use when a detail is missing; give real options if known)",
      {"question": "one short question", "options": "optional: choices separated by ;"}, read_only=True)
def _ask_user(ctx, question, options=""):
    choices = [o.strip() for o in options.split(";") if o.strip()]
    return ToolResult(True, question, {"end": "ask", "options": choices})


@tool("done", "finish: say one short sentence to the user", {"say": "the reply", "ok": "optional: false if it didn't work"},
      read_only=True)
def _done(ctx, say, ok="true"):
    return ToolResult(ok.lower() not in ("false", "no", "0"), say, {"end": "done"})
