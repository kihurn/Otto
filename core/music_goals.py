"""Deterministic single-goal Spotify compilation. No model or effects here."""
import re

from core.details import Intent, _t, music_intent


def unbound_music_reference(query: str) -> bool:
    return bool(re.fullmatch(r'(?:the )?(?:first|second|third|last|next) (?:result|song|track)|it|that|this',
                             query.strip().lower()))
