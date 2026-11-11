"""One-off check (agent core plan, task 1): does local Qwen answer Ollama's native "tools" field through C0RE?

Run on the PC:  python tools\\tool_call_probe.py
It sends one short request and prints what came back, how long it took, and the context size Otto asks for.
Nothing on your PC is touched.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import config  # noqa: E402

TOOLS = [{"type": "function", "function": {
    "name": "open", "description": "Open an app, file, folder or website.",
    "parameters": {"type": "object", "properties": {"what": {"type": "string"}}, "required": ["what"]}}}]


def main() -> int:
    settings = config.load_settings()
    key = config.c0re_key()
    if not key:
        print("OTTO_C0RE_KEY is not set (.env).")
        return 1
    model = settings["brains"]["decide"][0]
    num_ctx = int(settings.get("brain", {}).get("num_ctx", 32768))
    body = {"model": model, "stream": False, "tools": TOOLS, "options": {"num_ctx": num_ctx},
            "messages": [{"role": "user", "content": "open youtube"}]}
    req = urllib.request.Request(settings.get("c0re_url", "http://127.0.0.1:7080").rstrip("/") + "/api/chat",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as e:  # show the reason, never the key
        print(f"Request failed: {type(e).__name__}: {str(e)[:200]}")
        return 1
    msg = out.get("message") or {}
    print(f"model {model}, num_ctx {num_ctx}, {time.perf_counter() - t0:.1f} s")
    print("native tool_calls:", json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else "none")
    print("text:", (msg.get("content") or "")[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
