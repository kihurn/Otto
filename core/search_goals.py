"""Explicit web requests precede statistical area routing."""
import re
from core.details import _t


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
