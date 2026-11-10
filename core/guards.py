"""Quick checks that run before Laya: wake word, gibberish, yes/no replies, cancel, save/forget."""

from __future__ import annotations

import re

_WAKE = re.compile(r"^\s*(?:(?:hey|hi|ok|okay|yo)\s+)?(?:otto|auto|otto's|oto|otter|auto's)\b[\s,.:!?-]*", re.I)

YES = {"yes", "yeah", "yea", "ya", "yep", "yup", "sure", "ok", "okay", "k", "correct", "right",
       "please", "do it", "go ahead", "go for it", "yes please", "sure thing", "affirmative",
       "absolutely", "of course", "that's right", "thats right", "exactly", "ye", "yh", "mhm",
       "uh huh", "sounds good", "perfect", "go", "yes do it", "yeah do it", "yeah go ahead"}
NO = {"no", "nope", "nah", "no thanks", "don't", "dont", "do not", "cancel", "stop", "wrong",
      "not that", "no no", "nah nah", "never mind", "nevermind", "no thank you", "negative",
      "that's wrong", "thats wrong", "neither", "none"}
CANCEL = {"stop", "cancel", "never mind", "nevermind", "forget it", "abort", "quit it", "shut up"}

_SAVE = re.compile(r"^(?:(?:yeah|yes|yep|ok|okay|nice|great|perfect|good job|that worked|that was right|"
                   r"that's right|thats right)[,!.]?\s+)?(?:save|remember|keep|learn)\s+(?:that|this|it)\b"
                   r"(?:\s+(?:one|method|recipe|way))?(?:\s+for next time)?\s*[.!]*$", re.I)
_FORGET = re.compile(r"^(?:that was wrong,? |no,? )?(?:forget|delete|remove|wipe|unlearn|undo)\s+"
                     r"(?:that|this|it|what you (?:just )?(?:did|learned))\b.*$", re.I)


def clean(text: str) -> str:
    return " ".join((text or "").strip().split())


def strip_wake(text: str) -> tuple[str, bool]:
    """'Otto, open spotify' -> ('open spotify', True). Whisper often hears 'Otto' as 'auto'."""
    m = _WAKE.match(text)
    if not m:
        return text, False
    rest = text[m.end():].strip()
    return (rest, True) if rest else (text, True)


def wake_rest(text: str, wake_words: list[str]) -> str | None:
    """If the sentence starts with a wake phrase ("Hey Otto, ..."), return what comes after it
    (possibly ""). Otherwise None."""
    s = re.sub(r"[^a-z0-9' ]", " ", text.lower())
    s = " ".join(s.split())
    for w in sorted(wake_words, key=len, reverse=True):
        w = " ".join(re.sub(r"[^a-z0-9' ]", " ", w.lower()).split())
        if s == w or s.startswith(w + " "):
            # cut the same number of words from the original text, keeping its punctuation and case
            n = len(w.split())
            parts = re.split(r"(\s+)", text.strip())
            words_seen, i = 0, 0
            while i < len(parts) and words_seen < n:
                if parts[i].strip():
                    words_seen += 1
                i += 1
            return "".join(parts[i:]).strip(" ,.!?:-")
    return None


def _simple(text: str) -> str:
    return re.sub(r"[^a-z' ]", "", text.lower()).strip()


def reply_kind(text: str) -> str | None:
    """'yes', 'no', or None for anything that isn't a short yes/no answer."""
    s = _simple(text)
    if not s or len(s.split()) > 5:
        return None
    if s in YES or any(s.startswith(y + " ") for y in ("yes", "yeah", "yep", "yup", "sure", "ok", "okay")):
        if not any(w in s.split() for w in ("no", "not", "dont", "don't")):
            return "yes"
    if s in NO:
        return "no"
    if s.split()[0] in ("no", "nope", "nah"):
        rest = [w for w in s.split()[1:] if w not in ("no", "nah", "nope", "thanks", "wait", "sorry", "its", "it's", "not", "that")]
        return None if rest else "no"   # "no wait, open discord" is a new request, not just "no"
    return None


def is_cancel(text: str) -> bool:
    return _simple(text) in CANCEL


def memory_command(text: str) -> str | None:
    """'save' / 'forget' for the common phrasings, so they never depend on Laya."""
    t = clean(text)
    if _SAVE.match(t):
        return "save"
    if _FORGET.match(t):
        return "forget"
    return None


def is_gibberish(text: str, known_words: set[str] | None = None) -> bool:
    """True if not one word is a real word (English, slang, or a known app/site name)."""
    from wordfreq import tokenize, zipf_frequency

    words = tokenize(text, "en")
    if not words:
        return not re.search(r"\w", text)
    known_words = known_words or set()
    return not any(zipf_frequency(w, "en") >= 1.5 or w in known_words for w in words)
