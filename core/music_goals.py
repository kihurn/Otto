"""Deterministic single-goal Spotify compilation. No model or effects here."""
import re

from core.details import Intent, _t, music_intent


def compile_music(text: str) -> Intent | None:
    t = _t(text)
    t = re.sub(r'^i (?:want|need) you to\s+', '', t)
    t = re.sub(r'^spotify\s+and\s+search\b', 'open spotify and search', t)
    if not (t.startswith('open spotify') or t.startswith('search')):
        return None
    # Mask quoted titles before checking for independent extra commands.
    outside = re.sub(r'"[^"]*"|“[^”]*”', 'TITLE', t)
    if re.search(r'\b(?:and|then)\s+(?:set|open|close|write|find|pause|turn|search)\b',
                 re.sub(r'^open spotify\s+(?:and|then)\s+', '', outside)):
        return None
    has_setup = bool(re.match(r'^open spotify\b', t))
    t = re.sub(r'^open spotify\s*[,]?\s+(?:(?:and|then)\s+)?', '', t)
    t = re.sub(r'\bspotify\s*,\s*', 'spotify ', t)
    m = re.fullmatch(r'(?:search|search for|search on spotify|search spotify for)\s+(.+?)\s+(?:and|then)\s+play (?:it|the song|the first result)', t)
    if m:
        query = re.sub(r'^(?:for\s+)', '', m[1])
        query = re.sub(r'\s+(?:in|on) spotify$', '', query)
        return music_intent('play ' + query)
    m = re.fullmatch(r'(?:search on spotify|search spotify for)\s+(.+)', t)
    if m:
        return Intent('apps', 'search_in_app', {'app': 'Spotify', 'query': m[1]})
    if re.match(r'^search and play\b', t):
        return music_intent(t)
    if has_setup:
        m = re.fullmatch(r'(?:search|look up|find)\s+(?:for\s+)?(.+)', t)
        if m:
            return Intent('apps', 'search_in_app', {'app': 'Spotify', 'query': m[1]})
    # Existing extraction handles play/search-and-play with an explicit title.
    if re.match(r'^(?:search and )?(?:play|put on|listen to)\b', t):
        return music_intent(t)
    return None


def unbound_music_reference(query: str) -> bool:
    return bool(re.fullmatch(r'(?:the )?(?:first|second|third|last|next) (?:result|song|track)|it|that|this',
                             query.strip().lower()))
