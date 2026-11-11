"""Explicit web requests precede statistical area routing."""
import re
from core.details import _t


def new_tab(text):
    """True for "open a new tab (on chrome)": a browser request, never a file search."""
    return bool(re.fullmatch(r'(?:open|make|start|create|give me)\s+(?:up\s+)?(?:a\s+|another\s+)?new\s+'
                             r'(?:chrome\s+|browser\s+)?tab'
                             r'(?:\s+(?:on|in)\s+(?:google\s+)?chrome|\s+(?:on|in)\s+(?:the|my)\s+browser)?', _t(text)))


def web_query(text):
    t = _t(text)
    m = re.fullmatch(r'(?:search(?: for| the web for)?|google|look up)\s+(.+)', t)
    if not m:
        return None
    query = m[1]
    if re.search(r'\b(?:in|on)\s+(?!google(?: chrome)?\b|chrome\b|the web\b|the internet\b)\w+', query):
        return None
    query = re.sub(r'\s+(?:in|on|using)\s+(?:google chrome|google|chrome|the web|the internet)$', '', query)
    if re.search(r'\b(?:and|then)\s+(?:open|play|set|close|write|search)\b', query):
        return None
    return query.strip(' "\'') or None
