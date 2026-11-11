"""The areas Laya chooses between, and the actions inside each area.

Area descriptions are short on purpose: Laya's options share a small text budget.
"""

AREAS = {
    "apps": "open, close or switch apps and windows, or do something inside an app",
    "media": "play, pause, skip music or video, change volume",
    "web": "open a website or search the web",
    "files": "find or open files and folders on this computer",
    "notes": "write or type text into Notepad or a note",
    "timer": "set, check or cancel a timer, alarm or reminder",
    "question": "a question to answer: time, date, facts, maths, news",
    "screen": "about what is on the screen or in the clipboard",
    "memory": "save, remember or forget how Otto did the last task",
    "chitchat": "greetings, thanks, small talk, or about Otto",
    "unsure": "unclear, incomplete, or something Otto cannot do",
}

AREA_QUESTION = {
    "area": {
        "type": "choice",
        "instructions": "This is a request to Otto, a desktop assistant. Which area is it?",
        "criteria": AREAS,
    }
}

# What each area can do. The details step picks one of these (rules first, brain if needed).
ACTIONS = {
    "apps": {
        "open": "open/launch/start an app",
        "switch_to": "bring an open app to the front",
        "minimise": "minimise a window",
        "close": "close/quit an app",
        "search_in_app": "search for something inside an app",
        "click_button": "click a named button in an app",
    },
    "media": {
        "play_music": "play a specific song, artist, album or playlist",
        "play_liked": "play my music / my liked songs",
        "now_playing": "what song is playing",
        "play": "play / resume",
        "pause": "pause / stop",
        "play_pause": "play or pause",
        "next": "next track",
        "previous": "previous track / replay",
        "volume_up": "louder",
        "volume_down": "quieter",
        "set_volume": "set volume to a number",
        "get_volume": "read the current volume without changing it",
        "mute": "mute or unmute",
    },
    "web": {
        "open_site": "open a website",
        "web_search": "search the web",
    },
    "files": {
        "find": "find files",
        "open": "open a file or folder",
    },
    "notes": {
        "new_note": "write a new note",
        "add_to_note": "add to the last note",
    },
    "timer": {
        "set_timer": "a timer for a length of time",
        "set_alarm": "an alarm or reminder at a clock time",
        "time_left": "how long is left",
        "cancel": "cancel timers",
    },
}

# What Otto says when it asks "did you mean ...?" for each area (middle zone).
AREA_PHRASES = {
    "apps": "do something with an app",
    "media": "control the music or volume",
    "web": "open a website or search the web",
    "files": "find a file",
    "notes": "write a note",
    "timer": "set a timer or reminder",
    "question": "answer a question",
    "screen": "look at your screen",
    "memory": "save or forget what I just did",
    "chitchat": "just chat",
    "unsure": "do something I can't do yet",
}
