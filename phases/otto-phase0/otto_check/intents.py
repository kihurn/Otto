"""The first question Laya answers for every request: which area is this?

Descriptions are kept short on purpose: Laya's options share a small text budget,
and long descriptions get cut off.
"""

DOMAINS = {
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

DOMAIN_QUESTION = {
    "domain": {
        "type": "choice",
        "instructions": "This is a request to Otto, a desktop assistant. Which area is it?",
        "criteria": DOMAINS,
    }
}
