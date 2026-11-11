"""The brain's fallback chain against a fake C0RE server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


@pytest.fixture
def fake_c0re(monkeypatch):
    calls = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body["model"])
            if body["model"] == "cloud":
                self.send_response(402)
                self.end_headers()
                self.wfile.write(b'{"error":"this model is not included in your free usage"}')
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"message": {"content": '```json\n{"area": "apps"}\n```'}}).encode())

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OTTO_C0RE_KEY", "c0re_test")
    yield f"http://127.0.0.1:{srv.server_port}", calls
    srv.shutdown()


def test_fallback_and_cooldown(fake_c0re):
    from core.brain import Brain
    url, calls = fake_c0re
    b = Brain({"c0re_url": url, "brains": {"decide": ["cloud", "local"]}, "brain_timeout_s": 5})
    r = b.ask("decide", "x", want_json=True, required=("area",))
    assert r.data == {"area": "apps"} and r.model == "local" and calls == ["cloud", "local"]
    calls.clear()
    b.ask("decide", "x", want_json=True, required=("area",))
    assert calls == ["local"]   # the cloud model rests after its limit


def test_brief_is_included(fake_c0re):
    from core.brain import Brain
    b = Brain({"c0re_url": fake_c0re[0], "brains": {"decide": ["local"]}})
    b.context_fn = lambda: {"now": "NOW", "recent": "- (none)", "window": "W", "apps": "Spotify"}
    assert "Otto brief" in b.brief() and "NOW" in b.brief()


# ---- agent core, task 1: context size, multi-turn chat, local models only ----------------------

def _capture(monkeypatch):
    from core import brain as brain_mod
    bodies = []

    def fake_post(self, path, body, timeout):
        bodies.append(body)
        return {"message": {"content": '{"tool": "done", "args": {}}'}}

    monkeypatch.setattr(brain_mod.Brain, "_post", fake_post)
    return bodies


def test_num_ctx_sent_on_every_call(monkeypatch):
    from core.brain import Brain
    bodies = _capture(monkeypatch)
    b = Brain({"brains": {"decide": ["local"]}, "brain": {"num_ctx": 32768}})
    b.ask("decide", "hi", want_json=True)
    assert bodies[0]["options"]["num_ctx"] == 32768


def test_chat_keeps_callers_messages(monkeypatch):
    from core.brain import Brain
    bodies = _capture(monkeypatch)
    b = Brain({"brains": {"decide": ["local"]}, "brain": {"num_ctx": 16384}})
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    reply = b.chat(msgs, required=("tool",))
    assert bodies[0]["messages"] == msgs
    assert reply.data == {"tool": "done", "args": {}}


def test_default_chains_have_no_gemma():
    import json
    from core import config
    s = json.loads((config.DEFAULTS / "settings.json").read_text(encoding="utf-8"))
    assert all("gemma4:31b-cloud" not in chain for chain in s["brains"].values())
    assert s["brain"]["num_ctx"] == 32768


def test_migrate_v3_removes_gemma_from_user_chains():
    import json
    from core import config
    config.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SETTINGS_FILE.write_text(json.dumps({"_version": 2, "brains": {
        "decide": ["gemma4:31b-cloud", "qwen3-vl:8b-instruct"], "screen": ["gemma4:31b-cloud"]}}))
    settings = config.load_settings()
    mine = json.loads(config.SETTINGS_FILE.read_text())
    assert mine["_version"] == 3
    assert mine["brains"]["decide"] == ["qwen3-vl:8b-instruct"]
    assert "screen" not in mine["brains"]                     # empty chain removed, so the default applies
    assert "gemma4:31b-cloud" not in settings["brains"]["screen"]
