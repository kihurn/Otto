"""Questions: time and date and maths are answered locally and instantly; everything else goes to the
brain, with Ollama web search for anything that needs up-to-date facts."""

from __future__ import annotations

import ast
import json
import math
import operator
import re
import urllib.request
from datetime import datetime

from core import config

_NEEDS_WEB = re.compile(r"\b(who is|who's|who won|current|currently|latest|news|today'?s|tonight|tomorrow|"
                        r"weather|rain|temperature|forecast|price|worth|cost|stock|score|result|match|game|"
                        r"president|prime minister|ceo|released?|this week|this year|right now|holiday|"
                        r"convert|exchange rate|usd|myr|sgd|eur|gbp|bitcoin|crypto|open now|near me)\b", re.I)


def local_answer(text: str) -> str | None:
    t = re.sub(r"\bwhats\b", "what's", text.lower())
    now = datetime.now()
    if re.search(r"\bwhat(?:'s| is)? the time\b|\bwhat time is it\b|^time\??$|\bcurrent time\b", t):
        return f"It's {now:%I:%M %p}.".replace("It's 0", "It's ")
    if re.search(r"\bwhat(?:'s| is)? (?:the )?date\b|\bwhat(?:'s| is)? today\b|\bwhat day is it\b|\btoday's date\b", t):
        return f"It's {now:%A, %d %B %Y}.".replace(" 0", " ")
    if re.search(r"\bwhat year is it\b", t):
        return f"It's {now.year}."
    m = re.search(r"how many days (?:until|till|to) christmas", t)
    if m:
        xmas = datetime(now.year if (now.month, now.day) <= (12, 25) else now.year + 1, 12, 25)
        return f"{(xmas.date() - now.date()).days} days until Christmas."
    return maths(t)


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("too big")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "sqrt" and len(node.args) == 1:
        return math.sqrt(_eval(node.args[0]))
    raise ValueError("not maths")


def maths(text: str) -> str | None:
    t = text.lower().replace(",", "")
    t = re.sub(r"^(?:what(?:'s| is)|how much is|calculate|work out|whats)\s+", "", t).strip(" ?.")
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:percent|%)\s+of\s+(\d+(?:\.\d+)?)", r"(\1/100*\2)", t)
    t = re.sub(r"(?:the )?square root of\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", t)
    for a, b in (("multiplied by", "*"), ("times", "*"), ("divided by", "/"), ("over", "/"), ("plus", "+"),
                 ("minus", "-"), ("to the power of", "**"), ("squared", "**2"), ("cubed", "**3"), ("x", "*"), ("^", "**")):
        t = re.sub(rf"(?<=[\d)\s]){re.escape(a)}(?=[\s\d(])", f" {b} ", t) if a.isalpha() else t.replace(a, b)
    expr = t.strip()
    if not re.fullmatch(r"[\d\s.+\-*/()%sqrt]+", expr) or not re.search(r"\d", expr):
        return None
    if not re.search(r"[+\-*/%]|sqrt", expr):
        return None
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except Exception:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, float):
        value = round(value, 4)
    return f"That's {value:,}." if isinstance(value, int) else f"That's {value}."


def web_search(query: str, max_results: int = 3) -> list[dict]:
    key = config.ollama_key()
    if not key:
        return []
    req = urllib.request.Request("https://ollama.com/api/web_search",
                                 data=json.dumps({"query": query, "max_results": max_results}).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode()).get("results", [])
    except Exception:
        return []


STYLE = ("Answer in ONE short spoken-style sentence (under 25 words), no lists or markdown, because the "
         "answer may be read aloud.")


def answer(text: str, brain) -> tuple[str, str]:
    """Returns (answer, how): how = local / web+<model> / <model>."""
    quick = local_answer(text)
    if quick:
        return quick, "local"
    now = datetime.now().strftime("%A %d %B %Y, %H:%M")
    results = web_search(text) if _NEEDS_WEB.search(text) else []
    if results:
        context = "\n\n".join(f"[{i + 1}] {r.get('title', '')}\n{(r.get('content') or '')[:1200]}"
                              for i, r in enumerate(results))
        prompt = f"Today is {now}. Use these web search results to answer.\n\n{context}\n\nQuestion: {text}\n{STYLE}"
        how = "web"
    else:
        prompt = f"Today is {now}. Question: {text}\n{STYLE}"
        if _NEEDS_WEB.search(text):
            prompt += " If this needs up-to-date information you may not have, say so briefly."
        how = "memory"
    r = brain.ask("answer", prompt)
    return r.text, f"{how}+{r.model}"
