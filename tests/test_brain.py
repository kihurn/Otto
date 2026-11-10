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
