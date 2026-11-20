"""Explicit web requests precede statistical area routing."""
import re
from core.details import _t


def new_tab(text):
    """True for "open a new tab (on chrome)": a browser request, never a file search."""
    return bool(re.fullmatch(r'(?:open|make|start|create|give me)\s+(?:up\s+)?(?:a\s+|another\s+)?new\s+'
                             r'(?:chrome\s+|browser\s+)?tab'
                             r'(?:\s+(?:on|in)\s+(?:google\s+)?chrome|\s+(?:on|in)\s+(?:the|my)\s+browser)?', _t(text)))


