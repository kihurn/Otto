"""Fields Otto must never type into or read: passwords, card numbers, ID numbers, one-time codes.

This is enforced in code, not by asking a model nicely. It looks only at a control's label and type,
never at what is typed in it.

The word list is adapted from Nus Companion (companion/src/guide/sensitive.js, MIT licence);
see THIRD_PARTY_NOTICES.md.
"""
import re

_TEXT_TYPES = {'edit', 'combobox', 'textbox', 'password', 'document'}
_WORDS = re.compile(
    r"\b(password|passcode|passwd|pwd|pin|cvv|cvc|ssn|passport|otp)\b"
    r"|\b(?:card|credit|debit|account|routing|social security|national id|government id|tax id|ic|nric|"
    r"driver.?s? licen[cs]e)\s*(?:number|no|num)\b"
    r"|\b(?:credit|debit)\s*card\b"
    r"|\b(?:security|verification|one time)\s*code\b")


def sensitive(control: dict | None) -> bool:
    """True if this control is a password box or is labelled like one of the private fields above."""
    if not control:
        return False
    if control.get('password') is True:
        return True
    kind = str(control.get('type') or '').lower()
    if kind and kind not in _TEXT_TYPES:
        return False
    label = ' '.join(str(control.get(key) or '') for key in ('name', 'automation_id'))
    label = re.sub(r'([a-z])([A-Z])', r'\1 \2', label)       # "cardNumber" -> "card Number"
    label = re.sub(r'[_-]', ' ', label).lower()
    return bool(_WORDS.search(label))
