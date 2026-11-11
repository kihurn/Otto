"""Details: once the area is known, work out the action and its parameters.

Rules first (instant, predictable). If the rules can't tell, the brain (Qwen first) is asked to
fill in a small JSON form for that area. Either way the result is an Intent, which the planner
turns into named actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.areas import ACTIONS

WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
            "twenty five": 25, "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60,
            "seventy": 70, "eighty": 80, "ninety": 90, "one hundred": 100, "couple": 2, "few": 3}


@dataclass
class Intent:
    area: str
    action: str
    params: dict = field(default_factory=dict)
    source: str = "rules"            # rules / brain
    check_app: str | None = None     # "Did you mean <app>?" when the app name was a near match
    compose: str | None = None       # notes: ask the brain to write this first


def _t(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"^(?:can|could|would) you\s+(?:please\s+)?|^please\s+|^(?:i want to|i wanna|let's|lets)\s+", "", t)
    t = re.sub(r"\s*(?:please|pls|plz|for me|thanks|thank you)\s*[.!?]*$", "", t)
    return t.strip(" .!?")


# ---------------------------------------------------------------------------------------------
# Numbers, durations, clock times
# ---------------------------------------------------------------------------------------------

def _num(s: str) -> float | None:
    s = s.strip().lower().replace('-', ' ')
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    if s in WORD_NUM:
        return float(WORD_NUM[s])
    parts = s.split()
    if len(parts) == 2 and parts[0] in WORD_NUM and parts[1] in WORD_NUM:
        tens, ones = WORD_NUM[parts[0]], WORD_NUM[parts[1]]
        if tens in range(20, 100, 10) and 1 <= ones <= 9:
            return float(tens + ones)
    return None


_UNIT = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60,
         "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}
_NUMWORD = r"\d+(?:\.\d+)?|" + "|".join(sorted(WORD_NUM, key=len, reverse=True))


def parse_duration(text: str) -> float | None:
    t = text.lower()
    total = 0.0
    if re.search(r"\bhalf an? hour\b", t):
        total += 1800
        t = re.sub(r"\bhalf an? hour\b", "", t)
    if re.search(r"\b(?:an? )?hour and a half\b", t):
        total += 5400
        t = re.sub(r"\b(?:an? )?hour and a half\b", "", t)
    for m in re.finditer(rf"\b({_NUMWORD})\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|[smh])\b", t):
        n = _num(m.group(1))
        if n is not None:
            total += n * _UNIT[m.group(2)]
    if not total and re.search(r"\bpomodoro\b", t):
        total = 25 * 60
    return total or None


def parse_clock(text: str) -> str | None:
    t = text.lower().replace(".", "")
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m:
        h, mi = int(m.group(1)) % 12, int(m.group(2) or 0)
        if m.group(3) == "pm":
            h += 12
        return f"{h:02d}:{mi:02d}"
    m = re.search(r"\b(?:at|for)\s+(\d{1,2})(?::(\d{2}))?\b(?!\s*(?:min|sec|hour|%))", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h > 23 or mi > 59:
            return None
        if h <= 12 and "morning" not in t:
            from datetime import datetime
            now = datetime.now()
            if (h, mi) <= (now.hour, now.minute) and h + 12 <= 23:
                h += 12  # "at 3" in the afternoon means 15:00
        if "night" in t or "evening" in t or "afternoon" in t:
            h = h + 12 if h < 12 else h
        return f"{h:02d}:{mi:02d}"
    if "noon" in t:
        return "12:00"
    if "midnight" in t:
        return "00:00"
    return None


# ---------------------------------------------------------------------------------------------
# Per-area rules
# ---------------------------------------------------------------------------------------------

def _apps(text: str, apps) -> Intent | None:
    t = _t(text)
    if re.search(r"\bplay\b|\blisten to\b|\bput on\b", t) and not re.search(r"\b(?:youtube|netflix|steam)\b", t):
        music = music_intent(text)
        if music:
            return music
    # "click the play button in spotify"
    m = re.search(r"\b(?:click|press|tap|hit)(?: on)?\s+(?:the\s+)?(?P<b>.+?)(?:\s+button)?(?:\s+(?:in|on)\s+(?P<app>.+))?$", t)
    if m and m.group("app"):
        return Intent("apps", "click_button", {"app": m.group("app").strip(), "button": m.group("b").strip()})
    # "search for drake on spotify", "spotify search lofi", "open spotify and search lofi", "open up lofi beats on spotify"
    for pat in (r"^(?:open|launch|go to|pull up)?\s*(?:up\s+)?(?P<app>.+?)\s+and\s+(?:search|look up|find|look for)\s+(?:for\s+)?(?P<q>.+)$",
                r"^(?:search|look up|look for|find)\s+(?:for\s+)?(?P<q>.+?)\s+(?:on|in)\s+(?P<app>[\w .'-]+)$",
                r"^(?:in\s+)?(?P<app>spotify|steam|youtube|netflix|settings)\s+(?:search|look up|find)\s+(?:for\s+)?(?P<q>.+)$",
                r"^(?:open|play|put on|pull up|open up|throw on|chuck on)\s+(?:up\s+)?(?:some\s+)?(?P<q>.+?)\s+(?:on|in)\s+(?P<app>spotify|youtube|netflix|steam)$"):
        m = re.search(pat, t)
        if m:
            return Intent("apps", "search_in_app", {"app": m.group("app").strip(), "query": m.group("q").strip()})
    if re.search(r"\bminimi[sz]e\b|\bhide\b", t):
        spoken, _ = apps.find_in_text(t)
        return Intent("apps", "minimise", {"app": spoken or ""})
    action = "open"
    if re.search(r"\b(?:close|quit|exit|kill|shut down|shut)\b", t):
        action = "close"
    elif re.search(r"\b(?:switch|swap|go back|bring up|focus|jump|flip)\b", t):
        action = "switch_to"
    spoken, score = apps.find_in_text(t)
    if not spoken:
        return None
    found, mscore, _ = apps.match(spoken)
    if not found:
        return None
    intent = Intent("apps", action, {"app": found["name"]})
    if min(score, mscore) < 90 and found["name"].lower() != spoken.lower():
        intent.check_app = found["name"]
    return intent


_GENERIC_MUSIC = {"music", "the music", "some music", "it", "this", "that", "something", "a song", "songs", "again",
                  "the song", "spotify", "on spotify", "it again", "this song", "that song", "the video", "video"}
_NOW_PLAYING = re.compile(r"what(?:'s|s| is)\s+(?:this song|playing|this track|the song|on)\b|what song is (?:this|playing|on)|"
                          r"who (?:sings|is singing|sang) (?:this|that)|name of (?:this|the) song|what am i listening to")
_LIKED = re.compile(r"\b(?:play|put on|shuffle|start|throw on|chuck on)\b.*?\b(?:my (?:music|songs|liked songs|likes|"
                    r"favou?rites|library|tunes)|liked songs|songs i like|music i like)\b")


def music_intent(text: str) -> Intent | None:
    """Spotify-style requests, wherever they appear in a sentence (also inside longer requests like
    'open spotify, search and play "the hills" by "the weeknd"')."""
    t = _t(text)
    if _NOW_PLAYING.search(t):
        return Intent("media", "now_playing")
    m = re.search(r"\bmy playlist(?:\s+(?:called|named))?\s+(?P<q>.+?)(?:\s+on spotify)?$", t)
    if m and re.search(r"\b(?:play|put on|shuffle|start)\b", t):
        return Intent("media", "play_music", {"query": m.group("q").strip(" \"'"), "kind": "playlist"})
    if _LIKED.search(t):
        return Intent("media", "play_liked")
    raw = text.strip()
    m = re.search(r"\b(?:play|put on|listen to|queue up)\s+[\"“](?P<q>[^\"”]+)[\"”](?:\s+by\s+[\"“]?(?P<a>[^\"”]+?)[\"”]?)?"
                  r"(?:\s+(?:on|in)\s+spotify)?\s*[.?!]*$", raw, re.I)
    if not m:
        m = re.search(r"\b(?:play|put on|throw on|chuck on|listen to|queue up)\s+(?:me\s+)?(?:some\s+)?"
                      r"(?P<k>the\s+song|the\s+track|the\s+album|the\s+playlist|the\s+artist|song|track|album|playlist|artist)?\s*"
                      r"(?P<q>.+?)(?:\s+by\s+(?P<a>.+?))?(?:\s+(?:on|in|using)\s+spotify)?\s*[.?!]*$", raw, re.I)
    if not m:
        return None
    q = m.group("q").strip(" \"'“”").strip()
    if q.lower() in _GENERIC_MUSIC or re.search(r"\b(?:on|in)\s+(?:youtube|netflix|chrome)\b", q, re.I):
        return None
    k = (m.groupdict().get("k") or "").lower().replace("the ", "").strip()
    kind = {"song": "track", "track": "track", "album": "album", "playlist": "playlist", "artist": "artist"}.get(k, "auto")
    artist = (m.group("a") or "").strip(" \"'“”")
    if artist:
        kind = "track" if kind == "auto" else kind
    return Intent("media", "play_music", {"query": q, "kind": kind, "artist": artist})


def _media(text: str) -> Intent | None:
    t = _t(text)
    if re.fullmatch(r'(?:list|show)(?: me)? (?:my |the |available )?(?:audio |sound )?outputs?(?: devices)?', t):
        return Intent('media', 'list_audio_outputs')
    if re.fullmatch(r"(?:which|what)(?: is| are|'s)? (?:the |my |current |default )*(?:audio |sound )?output(?: device)?(?: am i using)?", t):
        return Intent('media', 'get_audio_output')
    if re.fullmatch(r'undo (?:that |the |my )?(?:audio )?output(?: change)?', t):
        return Intent('media', 'undo_audio_output')
    device = re.fullmatch(r'make (?:my |the )?(.+?) (?:as )?(?:the )?default (?:audio |sound )?output', t)
    if not device:
        device = re.fullmatch(r'(?:set|switch|change) (?:my |the )?(?:default )?(?:audio |sound )?output to (.+)', t)
    if device:
        return Intent('media', 'set_audio_output', {'device': device[1]})
    # Whisper often spells amounts: normalize numeric phrases only after to/at/by.
    def spoken_amount(match):
        value = _num(match[2])
        return match[1] + ' ' + str(int(value)) if value is not None else match[0]
    amounts = r'(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[ -](?:one|two|three|four|five|six|seven|eight|nine)|' + '|'.join(sorted(WORD_NUM, key=len, reverse=True))
    t = re.sub(r'\b(to|at|by)\s+(' + amounts + r')\b', spoken_amount, t)
    relative = re.search(r'\b(?:volume|sound)\b.*?\bby\s+(\d{1,3})(?:\s*(?:percent|%))?$', t)
    if relative and re.search(r'\b(?:increase|raise|lower|decrease|turn)\b', t):
        down = bool(re.search(r'\b(?:lower|decrease|down)\b', t))
        return Intent('media', 'volume_down' if down else 'volume_up', {'step': -int(relative[1]) if down else int(relative[1])})
    if re.search(r"\b(?:what|how|current|check|tell)\b.*\b(?:volume|sound level)\b", t):
        return Intent('media', 'get_volume')
    target = re.search(r'\b(?:volume|sound)\b.*?\b(?:to|at)\s+(\d{1,3})(?:\s*(?:percent|%))?$', t)
    if target:
        return Intent('media', 'set_volume', {'level': int(target[1])})
    m = re.search(r"(?:volume|sound)\s*(?:to|at|=)?\s*(\d{1,3})\s*%?|(\d{1,3})\s*(?:%|percent)\s*(?:volume)?", t)
    if m and ("volume" in t or "%" in t or "percent" in t or "sound" in t):
        return Intent("media", "set_volume", {"level": int(m.group(1) or m.group(2))})
    if re.search(r"\bun ?mute\b|\bmute\b", t):
        return Intent("media", "mute")
    if re.search(r"louder|turn (?:it|this|the volume|the music|that) up|volume up|crank|raise|increase|pump it", t):
        return Intent("media", "volume_up", {"step": 10})
    if re.search(r"quieter|softer|turn (?:it|this|the volume|the music|that) down|volume down|lower|decrease|too loud", t):
        return Intent("media", "volume_down", {"step": -10})
    if re.search(r"\b(?:next|skip)\b", t):
        return Intent("media", "next")
    if re.search(r"\b(?:previous|last song|last track|go back|replay|restart|back a song)\b", t):
        return Intent("media", "previous")
    music = music_intent(text)
    if music:
        return music
    if re.search(r"\b(?:pause|stop|hold on|shush)\b", t):
        return Intent("media", "pause")
    if re.search(r"\b(?:play|resume|unpause|continue|start)\b", t):
        return Intent("media", "play")
    return None


def _web(text: str) -> Intent | None:
    t = _t(text)
    m = re.search(r"^(?:search|look up|find)\s+(?P<site>youtube|netflix|steam|spotify)\s+for\s+(?P<q>.+)$", t)
    if m:
        return Intent("apps", "search_in_app", {"app": m.group("site"), "query": m.group("q")})
    m = re.search(r"^(?:google|search(?: up)?(?: the web| online| google| the internet)?(?: for)?|look up|look for|find)\s+"
                  r"(?:for\s+)?(?P<q>.+?)(?:\s+(?:online|on google|on the web|on the internet))?$", t)
    if m:
        return Intent("web", "web_search", {"query": m.group("q")})
    m = re.search(r"^(?:open|go to|go on|take me to|browse(?: to)?|visit|load|pull up|bring up|show me)\s+"
                  r"(?:up\s+)?(?:the\s+)?(?:my\s+)?(?P<s>.+?)(?:\s+(?:website|site|page|homepage))?"
                  r"(?:\s+(?:in (?:a )?new tab|in chrome|in the browser|on chrome))?$", t)
    if m:
        return Intent("web", "open_site", {"site": m.group("s").strip()})
    return None


_FILE_EXT = {r"\bscreenshots?\b": "screenshot ext:png;jpg;jpeg", r"\bpdfs?\b": "ext:pdf", r"\bexcel\b|\bspreadsheet\b|\bxlsx\b": "ext:xlsx;xls;csv",
             r"\bpowerpoint\b|\bslides\b|\bpptx?\b": "ext:pptx;ppt", r"\bword doc(?:ument)?s?\b|\bdocx\b": "ext:docx;doc",
             r"\bzips?\b": "ext:zip;rar;7z", r"\bvideos?\b|\bmp4s?\b": "ext:mp4;mkv;mov;avi",
             r"\bphotos?\b|\bpictures?\b|\bimages?\b": "ext:png;jpg;jpeg;webp;heic"}
_FILE_FILLER = r"\b(?:find|search(?: my (?:pc|computer|laptop))?(?: for)?|locate|where(?:'s| is| did i (?:save|put))|open|show me|" \
               r"get|my|the|a|an|all|any|for|files?|folders?|named|called|with|in the name|that i|i|took|made|" \
               r"recorded|saved|this morning|today|yesterday|last week|latest|most recent|newest|last|recent|" \
               r"on|in|from|of|to|is|are|me|computer|pc|desktop|downloads?|documents?)\b"


def _files(text: str) -> Intent | None:
    from hands import files
    t = _t(text)
    folder = files.known_folder(t)
    if folder:
        return Intent("files", "open", {"path": folder})
    filters = [v for k, v in _FILE_EXT.items() if re.search(k, t)]
    words = t
    for k in _FILE_EXT:
        words = re.sub(k, " ", words)
    named = re.search(r"(?:called|named)\s+(.+?)(?:\s+(?:in|on|from)\s+(?:my\s+|the\s+)?\w+)?$", t)
    words = re.sub(_FILE_FILLER, " ", words)
    words = " ".join(w for w in re.findall(r"[\w.'-]+", words) if len(w) > 1 or w.isdigit())
    if named:
        words = named.group(1)
    query = " ".join([words] + filters).strip()
    if not query:
        return None
    latest = bool(re.search(r"\b(?:latest|most recent|newest|last)\b", t))
    action = "open" if (t.startswith("open") or latest) else "find"
    return Intent("files", action, {"query": query, "first": latest or bool(named)})


_COMPOSE = re.compile(r"\b(?:write|draft|compose|make|create)\s+(?:me\s+)?(?:a|an|some)\s+(?:short\s+|quick\s+|little\s+)?"
                      r"(?:poem|paragraph|story|essay|email|e-mail|message|summary|letter|speech|list of|plan|outline)\b")


def _notes(text: str) -> Intent | None:
    t_raw = text.strip()
    t = _t(text)
    if _COMPOSE.search(t):
        return Intent("notes", "new_note", {}, compose=re.sub(r"\s+in (?:a )?(?:notepad|note)$", "", t))
    m = re.search(r"^(?:write|make|create|start|open)\s+(?:me\s+)?(?:a\s+|an\s+|my\s+)?(?:quick\s+|new\s+)?"
                  r"(?P<n>(?:to-?\s?do|shopping|grocery|groceries|packing|check)\s*list)(?:\s+in notepad)?$", t)
    if m:
        return Intent("notes", "new_note", {"text": "", "title": m.group("n")})
    m = re.search(r"\badd\s+(?P<x>.+?)\s+to\s+(?:my |the )?(?:\w+\s+)?(?:note|list)\b", t)
    if m:
        return Intent("notes", "add_to_note", {"text": m.group("x")})
    m = re.search(r"(?:new|create a|make a|start a)\s+(?:new\s+)?(?:note|text file|file)\s+(?:called|named)\s+(?P<n>.+)$", t)
    if m:
        return Intent("notes", "new_note", {"text": "", "title": m.group("n")})
    # Keep the user's own capitalisation for the note text
    m = re.search(r"(?::\s*|\b(?:saying|that says|that|type|write|jot down|note down|put|type out)\s+)(?P<x>.+)$", t_raw, re.I)
    if m:
        x = re.sub(r"\s+(?:in|into|on)\s+(?:notepad|a note|my notes?)\s*$", "", m.group("x"), flags=re.I)
        x = re.sub(r"^(?:this|down|that)\s*:?\s*", "", x, flags=re.I).strip(" \"'")
        if x and x.lower() not in ("this", "it", "that", "something"):
            return Intent("notes", "new_note", {"text": x})
    return None


def _timer(text: str) -> Intent | None:
    t = _t(text)
    if re.search(r"\b(?:cancel|stop|delete|clear|turn off|remove)\b.*\b(?:timers?|alarms?|reminders?|countdown)\b", t):
        return Intent("timer", "cancel")
    if re.search(r"how (?:long|much time)|time (?:left|remaining)|left on|remaining", t):
        return Intent("timer", "time_left")
    label = ""
    m = re.search(r"\bto\s+(?P<l>(?!\d)[^,.]+?)(?:\s+(?:in|at|every|tomorrow)\b.*)?$", t) if "remind" in t else None
    if m:
        label = m.group("l").strip()
    else:
        m = re.search(r"\bfor (?:the |my )?(?P<l>(?!\d)(?!a\b)(?!an\b)[a-z][a-z ]+?)$", t)
        if m and not parse_duration(m.group("l")):
            label = m.group("l").strip()
    secs = parse_duration(t)
    if secs:
        return Intent("timer", "set_timer", {"seconds": secs, "label": label})
    at = parse_clock(t)
    if at:
        return Intent("timer", "set_alarm", {"at": at, "label": label})
    return None


def by_rules(area: str, text: str, apps) -> Intent | None:
    try:
        if area in ("question", "chitchat", "web") and _NOW_PLAYING.search(_t(text)):
            return Intent("media", "now_playing")
        if area == "apps":
            return _apps(text, apps)
        if area == "media":
            return _media(text)
        if area == "web":
            return _web(text)
        if area == "files":
            return _files(text)
        if area == "notes":
            return _notes(text)
        if area == "timer":
            return _timer(text)
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------------------------
# Brain fallback
# ---------------------------------------------------------------------------------------------

PARAMS = {
    "apps": "app (the app's name), query (for search_in_app), button (for click_button)",
    "media": "level (0-100, for set_volume), query + kind (track/artist/album/playlist) + artist (for play_music)",
    "web": "site (for open_site), query (for web_search)",
    "files": "query (words in the file name)",
    "notes": "text (exactly what to write), title (optional)",
    "timer": "seconds (for set_timer), at (HH:MM 24-hour, for set_alarm), label (what it's for)",
}


def by_brain(area: str, text: str, brain) -> Intent | None:
    acts = ACTIONS.get(area)
    if not acts:
        return None
    menu = "\n".join(f"- {k}: {v}" for k, v in acts.items())
    prompt = (f"A user said to their desktop assistant: \"{text}\"\n"
              f"It is about: {area}.\nPick ONE action:\n{menu}\n"
              f"Possible parameters: {PARAMS[area]}.\n"
              "Reply with only JSON: {\"action\": \"...\", \"params\": {...}}. "
              "Use the user's own words for names and search terms. If it can't be done, use \"action\": \"none\".")
    try:
        r = brain.ask("extract", prompt, want_json=True, required=("action",))
    except Exception:
        return None
    action = str(r.data.get("action", "")).strip()
    if action not in acts:
        return None
    params = r.data.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    return Intent(area, action, params, source=f"brain:{r.model}")
