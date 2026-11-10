"""The brain: language models through C0RE, with automatic fallback.

Each job (extract, decide, screen, answer, chat) has its own ordered list of models in
settings.json. If a model is out of quota, offline, too slow or not allowed, Otto moves to the
next one straight away. The brain never runs anything itself: it only returns text or JSON.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from core import config


class BrainError(Exception):
    def __init__(self, code: str, message: str, retry_after: str | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.retry_after = retry_after


class NoBrainAvailable(Exception):
    """Every model in the chain failed. .reasons says why, model by model."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


# These mean the key itself is wrong: no point trying other models.
FATAL = {"invalid_key", "key_disabled", "no_key"}

FIXES = {
    "invalid_key": "Your C0RE key wasn't accepted. Make a new one in the C0RE dashboard and save it again (README step 2).",
    "key_disabled": "Your C0RE key is switched off in the C0RE dashboard.",
    "no_key": "OTTO_C0RE_KEY isn't set (README step 2). Open a new PowerShell window after setting it.",
    "unreachable": "C0RE isn't answering on this PC. Is it running?",
}


@dataclass
class BrainReply:
    text: str
    data: dict | None
    model: str
    seconds: float


def _strip_json(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    if not t.startswith("{"):
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            t = m.group(0)
    return t


class Brain:
    def __init__(self, settings: dict):
        self.settings = settings
        self.url = settings.get("c0re_url", "http://127.0.0.1:7080").rstrip("/")
        self.timeout = float(settings.get("brain_timeout_s", 12))
        self.cooldown: dict[str, float] = {}  # model -> time it may be tried again

    # ---- low level -----------------------------------------------------------------------
    def _post(self, path: str, body: dict, timeout: float) -> dict:
        key = config.c0re_key()
        if not key:
            raise BrainError("no_key", "OTTO_C0RE_KEY is not set")
        req = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            code, msg = f"http_{e.code}", raw[:200]
            try:
                err = json.loads(raw).get("error")
                if isinstance(err, dict):
                    code, msg = err.get("code", code), err.get("message", msg)
                elif isinstance(err, str):
                    msg = err
                    if e.code == 402 or "usage" in err.lower() or "quota" in err.lower():
                        code = "quota"
                    elif "not found" in err.lower():
                        code = "model_not_found"
            except Exception:
                pass
            if e.code == 429:
                code = code if code != f"http_{e.code}" else "rate_limited"
            raise BrainError(code, msg, e.headers.get("Retry-After")) from None
        except urllib.error.URLError as e:
            raise BrainError("unreachable", str(e.reason)) from None
        except TimeoutError:
            raise BrainError("timeout", f"no answer in {timeout:.0f}s") from None

    def _chat_once(self, model: str, messages: list[dict], want_json: bool, timeout: float) -> str:
        body = {"model": model, "messages": messages, "stream": False,
                "options": {"temperature": 0.2 if want_json else 0.6}}
        if want_json:
            body["format"] = "json"
        out = self._post("/api/chat", body, timeout)
        return ((out.get("message") or {}).get("content") or "").strip()

    # ---- what the rest of Otto uses -------------------------------------------------------
    def ask(self, job: str, prompt: str, system: str | None = None, images: list[str] | None = None,
            want_json: bool = False, required: tuple[str, ...] = (), timeout: float | None = None) -> BrainReply:
        """Ask the first working model for this job. Raises NoBrainAvailable if all fail."""
        chain = self.settings.get("brains", {}).get(job) or self.settings["brains"]["decide"]
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        user = {"role": "user", "content": prompt}
        if images:
            user["images"] = images
        messages.append(user)
        reasons = []
        for model in chain:
            if self.cooldown.get(model, 0) > time.time():
                reasons.append(f"{model}: resting after a limit")
                continue
            t0 = time.perf_counter()
            try:
                text = self._chat_once(model, messages, want_json, timeout or self.timeout)
                data = None
                if want_json:
                    data = self._parse(text, required)
                    if data is None:  # one polite retry on the same model
                        retry = messages + [{"role": "assistant", "content": text},
                                            {"role": "user", "content": "Reply with only the JSON object, nothing else."}]
                        text = self._chat_once(model, retry, True, timeout or self.timeout)
                        data = self._parse(text, required)
                    if data is None:
                        reasons.append(f"{model}: reply wasn't valid JSON")
                        continue
                return BrainReply(text, data, model, time.perf_counter() - t0)
            except BrainError as e:
                reasons.append(f"{model}: {e.code}")
                if e.code in FATAL:
                    raise NoBrainAvailable([FIXES.get(e.code, e.message)]) from None
                if e.code in ("quota", "rate_limited"):
                    wait = 60.0
                    try:
                        wait = float(e.retry_after) if e.retry_after else (600.0 if e.code == "quota" else 60.0)
                    except ValueError:
                        pass
                    self.cooldown[model] = time.time() + wait
        raise NoBrainAvailable(reasons)

    @staticmethod
    def _parse(text: str, required: tuple[str, ...]) -> dict | None:
        try:
            data = json.loads(_strip_json(text))
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        if any(k not in data for k in required):
            return None
        return data
