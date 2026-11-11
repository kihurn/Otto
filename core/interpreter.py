"""Qwen as interpreter and supervisor.

Laya and the rules stay the fast path for plain, direct requests ("set volume to 30", "open spotify").
Whenever they don't give a clean answer, the request goes here: local Qwen reads the sentence together with
the last few turns, the app Otto last worked in and the window in front, and picks ONE thing from Otto's
menu of named actions. That is how "can you save this file" right after "open notepad" becomes "save, in
Notepad" instead of a file search.

Qwen still never runs anything. Its answer is checked against the menu below, turned into the same Intent
the rules produce, and then goes through the planner and the safety gate like every other request.
"""
from __future__ import annotations

import re

from core.details import Intent, _t

# What Qwen may choose: area.action -> (what it is, the parameters it takes).
MENU = {
    "apps.open": ("open or start an app", ("app",)),
    "apps.close": ("close an app", ("app",)),
    "apps.switch_to": ("bring an open app to the front", ("app",)),
    "apps.click_button": ("press one named button/menu/tab in an app", ("app", "button")),
    "apps.type_in_app": ("type the user's exact words into an app", ("app", "text")),
    "apps.app_goal": ("anything else done inside an app (save, export, change a setting...): Otto works out the "
                      "clicks. goal = what the user wants, in their words", ("app", "goal")),
    "media.play_music": ("play a song, artist, album or playlist; kind is track/artist/album/playlist",
                         ("query", "artist", "kind")),
    "media.play": ("resume playback", ()),
    "media.pause": ("pause playback", ()),
    "media.next": ("skip to the next song / change the song", ()),
    "media.previous": ("go back to the previous song", ()),
    "media.now_playing": ("say what is playing", ()),
    "media.set_volume": ("set the volume; level is 0-100", ("level",)),
    "media.volume_up": ("louder", ()),
    "media.volume_down": ("quieter", ()),
    "web.open_site": ("open a website", ("site",)),
    "web.web_search": ("open a web search in Chrome; ONLY when they say search, google or look up", ("query",)),
    "files.find": ("find a file or folder on the PC by name", ("query",)),
    "notes.new_note": ("write a new note; text = the user's exact words to write down", ("text",)),
    "timer.set_timer": ("start a timer; seconds = its length", ("seconds", "label")),
    "question.answer": ("the user asks something Otto should answer in words (facts, who/what/when/how old, "
                        "the weather, maths); Otto looks it up itself", ()),
    "chitchat.reply": ("small talk", ()),
    "ask.clarify": ("you cannot tell what they want: put ONE short question in \"question\"", ()),
}
# Words the user must have actually said before Qwen's "exact words" are typed or written anywhere.
_QUOTED = {"apps.type_in_app": "text", "notes.new_note": "text"}


def build_prompt(text: str, history: list[dict], last_app: str, window: str) -> str:
    recent = "\n".join(f"User: {h['you']}\nOtto: {h['otto'][:140]}" for h in history[-4:]) or "(nothing yet)"
    menu = "\n".join(f"- {name}: {what}" + (f" [params: {', '.join(params)}]" if params else "")
                     for name, (what, params) in MENU.items())
    return (
        "You decide what a desktop assistant should do for its user. Read the new request together with the "
        "recent conversation: words like \"this\", \"it\", \"that file\" usually refer to the app or thing just "
        "mentioned.\n"
        f"Recent conversation:\n{recent}\n"
        f"App Otto last worked in: {last_app or 'none'}\n"
        f"Window in front: {window or 'unknown'}\n"
        f"New request: \"{text}\"\n\n"
        f"Choose exactly one:\n{menu}\n\n"
        "Rules: speech recognition may have misheard a word; prefer the reading that makes sense. "
        "If the request is about something inside an app (save, export, undo, a menu or setting), use "
        "apps.app_goal with that app, not files.find. Only use notes.new_note when they clearly want something "
        "written down. Never invent words for text. If you really cannot tell, use ask.clarify.\n"
        'Reply with JSON only: {"choice": "<area.action>", "params": {...}, "sure": true or false, '
        '"question": "<only for ask.clarify>"}'
    )


def _said(words: str, text: str) -> bool:
    """Did the user actually say these words? (Compared without punctuation or capitals.)"""
    flat = lambda s: " ".join(re.findall(r"\w+", s.lower()))
    return bool(flat(words)) and flat(words) in flat(text)


def to_intent(reply, text: str, apps, last_app: str = "") -> tuple[Intent | None, str, bool]:
    """Turn Qwen's reply into (intent, question, sure). Anything off the menu becomes (None, '', False)."""
    if not isinstance(reply, dict):
        return None, "", False
    choice = str(reply.get("choice") or "").strip()
    params = reply.get("params") if isinstance(reply.get("params"), dict) else {}
    sure = reply.get("sure") is True
    if choice == "ask.clarify":
        return None, str(reply.get("question") or "").strip()[:160], False
    if choice not in MENU:
        return None, "", False
    area, action = choice.split(".", 1)
    allowed = MENU[choice][1]
    params = {k: v for k, v in params.items() if k in allowed and v not in (None, "")}
    if area in ("question", "chitchat"):
        return Intent(area, area, {}, source="brain"), "", sure
    if area == "apps":
        named = " ".join(str(params.get("app") or last_app or "").lower().split())
        found = apps.match_exact(named) if apps is not None and named else None
        if not found and apps is not None and named:
            best, score, _ = apps.match(named)
            found = best if best and score >= 85 else None
        if not found:
            return None, "Which app do you mean?", False
        params["app"] = found["name"] if isinstance(found, dict) else named
        if action in ("click_button", "type_in_app", "app_goal") and not params.get(
                {"click_button": "button", "type_in_app": "text", "app_goal": "goal"}[action]):
            return None, "", False
    key = _QUOTED.get(choice)
    if key and not _said(str(params.get(key, "")), text):
        return None, "", False                       # Qwen made up the words: do not type or write them
    if choice == "media.set_volume":
        try:
            params["level"] = max(0, min(100, int(float(params["level"]))))
        except (KeyError, TypeError, ValueError):
            return None, "", False
    if choice == "timer.set_timer":
        try:
            params["seconds"] = float(params["seconds"])
        except (KeyError, TypeError, ValueError):
            return None, "", False
    if choice in ("media.play_music", "web.web_search", "web.open_site", "files.find") and not (
            params.get("query") or params.get("site")):
        return None, "", False
    return Intent(area, action, params, source="brain"), "", sure


def interpret(text: str, history: list[dict], last_app: str, window: str, apps, brain) -> tuple[Intent | None, str, bool]:
    """Ask local Qwen what the user means. Returns (intent, question for the user, sure)."""
    schema = {"type": "object", "required": ["choice", "params", "sure"],
              "properties": {"choice": {"enum": list(MENU)}, "params": {"type": "object"},
                             "sure": {"type": "boolean"}, "question": {"type": "string"}}}
    reply = brain.ask("decide", build_prompt(text, history, last_app, window), want_json=schema,
                      required=("choice",), timeout=12)
    return to_intent(reply.data, text, apps, last_app)


# ---- when the fast path's answer should not be trusted ------------------------------------------------

def suspicious(intent: Intent | None, text: str) -> bool:
    """Cheap checks for answers that are probably wrong, so Qwen gets a look before Otto acts."""
    if intent is None:
        return True
    t = _t(text)
    if intent.area == "notes" and intent.action == "new_note":
        words = str(intent.params.get("text", ""))
        # A "note" whose text is the whole request ("Can you open Notepad?"), or with no note-like word at all.
        if _said(text, words) or not re.search(r"\b(?:note|write|jot|remember|remind|list|type)\b", t):
            return True
    if intent.area == "files" and re.match(r"(?:save|close|print|export|undo|redo|copy|paste|select|rename|share)\b", t):
        return True                                  # "save my file" is not a file search
    if intent.source == "brain" and intent.area == "media" and intent.action in ("play_pause", "play", "pause") \
            and re.search(r"\b(?:change|skip|next|another|different)\b", t):
        return True
    return False


# ---- after acting: what now? ------------------------------------------------------------------------

def build_review_prompt(text: str, did: str, result: str, app: str) -> str:
    return (
        "A desktop assistant tried to do what its user asked, and it did not clearly work.\n"
        f"The user asked: \"{text}\"\n"
        f"The assistant tried: {did}\n"
        f"What happened: {result}\n"
        f"App involved: {app or 'none'}\n\n"
        "Choose what the assistant should do next:\n"
        "- \"work_it_out\": look at that app's window and work out the clicks step by step (only if an app is involved)\n"
        "- \"ask\": ask the user ONE short, specific question (put it in \"question\")\n"
        "- \"leave\": the reply above already tells the user what they need\n"
        'Reply with JSON only: {"next": "work_it_out" | "ask" | "leave", "goal": "<what to achieve in the app, '
        'in the user\'s words>", "question": "<for ask>"}'
    )


def review(text: str, did: str, result: str, app: str, brain) -> dict:
    schema = {"type": "object", "required": ["next"],
              "properties": {"next": {"enum": ["work_it_out", "ask", "leave"]},
                             "goal": {"type": "string"}, "question": {"type": "string"}}}
    data = brain.ask("decide", build_review_prompt(text, did, result, app), want_json=schema,
                     required=("next",), timeout=10).data
    choice = data.get("next") if isinstance(data, dict) else None
    if choice == "work_it_out" and app:
        return {"next": "work_it_out", "goal": str(data.get("goal") or text)[:200]}
    if choice == "ask" and str(data.get("question") or "").strip():
        return {"next": "ask", "question": str(data["question"]).strip()[:160]}
    return {"next": "leave"}
