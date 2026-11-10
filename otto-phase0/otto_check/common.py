"""Shared helpers for the Otto Phase 0 checks.

Nothing in here ever prints or saves your C0RE key or Ollama API key.
"""

from __future__ import annotations

import json
import os
import shutil
import site
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
DATA_DIR = ROOT / "data"

# The models Otto will try, in order. Edit these lists if a name changes.
CLOUD_MODELS = [
    "gemma4:31b-cloud",
    "deepseek-v4.1-flash:cloud",
    "glm-5.3-flash:cloud",
    "kimi-k3.1-pro:cloud",
]
LOCAL_MODELS = [
    "qwen3-vl:8b-instruct",
    "qwen3-vl:4b-instruct",
]


# ----------------------------------------------------------------------------
# Printing
# ----------------------------------------------------------------------------

def _supports_colour() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


_C = _supports_colour()
GREEN = "\033[92m" if _C else ""
RED = "\033[91m" if _C else ""
YELLOW = "\033[93m" if _C else ""
BOLD = "\033[1m" if _C else ""
RESET = "\033[0m" if _C else ""


def title(text: str) -> None:
    print()
    print(f"{BOLD}== {text} =={RESET}")


def ok(text: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {text}")


def fail(text: str, fix: str | None = None) -> None:
    print(f"  {RED}FAIL{RESET}  {text}")
    if fix:
        print(f"        -> {fix}")


def warn(text: str) -> None:
    print(f"  {YELLOW}NOTE{RESET}  {text}")


def info(text: str) -> None:
    print(f"        {text}")


class Results:
    """Collects PASS/FAIL lines and numbers, then saves them to results/<name>.json."""

    def __init__(self, name: str):
        self.name = name
        self.checks: list[dict] = []
        self.numbers: dict = {}
        self.started = time.time()

    def passed(self, label: str, detail: str = "") -> None:
        ok(f"{label}" + (f": {detail}" if detail else ""))
        self.checks.append({"check": label, "result": "PASS", "detail": detail})

    def failed(self, label: str, detail: str = "", fix: str | None = None) -> None:
        fail(f"{label}" + (f": {detail}" if detail else ""), fix)
        self.checks.append({"check": label, "result": "FAIL", "detail": detail})

    def noted(self, label: str, detail: str = "") -> None:
        warn(f"{label}" + (f": {detail}" if detail else ""))
        self.checks.append({"check": label, "result": "NOTE", "detail": detail})

    def save(self) -> Path:
        RESULTS_DIR.mkdir(exist_ok=True)
        path = RESULTS_DIR / f"{self.name}.json"
        payload = {
            "check": self.name,
            "seconds": round(time.time() - self.started, 1),
            "python": sys.version.split()[0],
            "checks": self.checks,
            "numbers": self.numbers,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        n_fail = sum(1 for c in self.checks if c["result"] == "FAIL")
        n_pass = sum(1 for c in self.checks if c["result"] == "PASS")
        print()
        colour = GREEN if n_fail == 0 else RED
        print(f"{colour}{BOLD}{self.name}: {n_pass} passed, {n_fail} failed{RESET}  (saved to {path.relative_to(ROOT)})")
        return path

    @property
    def any_failed(self) -> bool:
        return any(c["result"] == "FAIL" for c in self.checks)


# ----------------------------------------------------------------------------
# GPU memory (read from nvidia-smi, so it includes Ollama and everything else)
# ----------------------------------------------------------------------------

def gpu_memory() -> dict | None:
    """Return {'name', 'used_mb', 'total_mb', 'free_mb'} or None if nvidia-smi is missing."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.used,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()[0]
        name, used, total, driver = [x.strip() for x in out.split(",")]
        used, total = int(float(used)), int(float(total))
        return {"name": name, "used_mb": used, "total_mb": total,
                "free_mb": total - used, "driver": driver}
    except Exception:
        return None


def gb(mb: float) -> str:
    return f"{mb / 1024:.2f} GB"


# ----------------------------------------------------------------------------
# CUDA libraries for faster-whisper (CTranslate2 needs cuBLAS 12 + cuDNN 9)
# ----------------------------------------------------------------------------

def add_nvidia_dll_dirs() -> list[str]:
    """Make the pip-installed NVIDIA DLLs findable on Windows. Returns the folders added."""
    added: list[str] = []
    if os.name != "nt":
        return added
    roots = [Path(p) / "nvidia" for p in site.getsitepackages() + [site.getusersitepackages()]]
    for root in roots:
        if not root.is_dir():
            continue
        for dll in root.rglob("*.dll"):
            folder = str(dll.parent)
            if folder not in added:
                added.append(folder)
    for folder in added:
        try:
            os.add_dll_directory(folder)
        except (OSError, AttributeError):
            pass
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")
    return added


# ----------------------------------------------------------------------------
# C0RE client (Ollama-style API behind C0RE)
# ----------------------------------------------------------------------------

class C0REError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: str | None = None):
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


ERROR_FIXES = {
    "invalid_key": "The key wasn't accepted. Re-create it in the C0RE dashboard and set OTTO_C0RE_KEY again (see README step 3).",
    "key_disabled": "This key is switched off. Turn it back on in the C0RE dashboard > Keys.",
    "model_not_allowed": "Allow this model for the 'otto' key in the C0RE dashboard > Keys > (your key) > Models.",
    "rate_limited": "C0RE's rate limit was hit. Wait a minute and run the check again.",
    "engine_offline": "Ollama isn't running. Open the Ollama app on the PC (or run 'ollama serve') and try again.",
}


def c0re_url() -> str:
    return os.environ.get("OTTO_C0RE_URL", "http://127.0.0.1:7080").rstrip("/")


def c0re_key() -> str | None:
    key = os.environ.get("OTTO_C0RE_KEY", "").strip()
    return key or None


def c0re_request(path: str, body: dict | None = None, timeout: float = 180) -> dict:
    key = c0re_key()
    if not key:
        raise C0REError(0, "no_key", "OTTO_C0RE_KEY is not set")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        c0re_url() + path,
        data=data,
        method="POST" if body is not None else "GET",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        code, message = f"http_{e.code}", raw[:300]
        try:
            err = json.loads(raw).get("error")
            if isinstance(err, dict):  # C0RE style: {"error":{"code","message"}}
                code, message = err.get("code", code), err.get("message", message)
            elif isinstance(err, str):  # plain Ollama style: {"error":"..."}
                message = err
                low = err.lower()
                if "not found" in low:
                    code = "model_not_found"
                elif "limit" in low or "quota" in low or e.code == 429:
                    code = "quota_or_limit"
        except Exception:
            pass
        raise C0REError(e.code, code, message, e.headers.get("Retry-After")) from None
    except urllib.error.URLError as e:
        raise C0REError(0, "unreachable", f"can't reach C0RE at {c0re_url()} ({e.reason})") from None
    except TimeoutError:
        raise C0REError(0, "timeout", f"no answer within {timeout:.0f}s") from None


def chat(model: str, prompt: str, images_b64: list[str] | None = None,
         fmt: str | dict | None = None, timeout: float = 180) -> tuple[str, float]:
    """One non-streaming chat turn. Returns (reply_text, seconds)."""
    msg: dict = {"role": "user", "content": prompt}
    if images_b64:
        msg["images"] = images_b64
    body: dict = {"model": model, "messages": [msg], "stream": False}
    if fmt is not None:
        body["format"] = fmt
    t0 = time.perf_counter()
    out = c0re_request("/api/chat", body, timeout=timeout)
    secs = time.perf_counter() - t0
    reply = (out.get("message") or {}).get("content", "") or ""
    return reply.strip(), secs


def fix_for(err: C0REError) -> str | None:
    if err.code in ERROR_FIXES:
        return ERROR_FIXES[err.code]
    if err.code == "no_key":
        return "Set OTTO_C0RE_KEY first (README step 3), then open a NEW PowerShell window."
    if err.code == "unreachable":
        return "Is C0RE running on the PC? Check http://127.0.0.1:7080/admin opens in a browser."
    if err.code == "model_not_found":
        return "Check the model name. For cloud models, make sure Ollama is signed in ('ollama signin')."
    if err.code == "quota_or_limit":
        return "Probably the Ollama cloud usage limit. Check https://ollama.com/settings/usage"
    return None


def require_key(results: Results) -> bool:
    if c0re_key():
        return True
    results.failed("C0RE key", "OTTO_C0RE_KEY is not set",
                   "Follow README step 3, then open a NEW PowerShell window and try again.")
    return False
