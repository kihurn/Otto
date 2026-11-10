"""Spotify through its official Web API (needs Premium for playback control).

Sign-in uses PKCE, the method meant for desktop apps: you approve Otto once in Chrome, and no
client secret is needed. The sign-in token is kept OUTSIDE OneDrive, in
C:\\Users\\<you>\\.otto\\spotify_token.json, because it controls your Spotify account.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets

import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core import config

REDIRECT = "http://127.0.0.1:8765/callback"
SCOPES = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
          "user-library-read playlist-read-private")
TOKEN_FILE = Path.home() / ".otto" / "spotify_token.json"
API = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------------------------

def configured() -> bool:
    return bool(config.spotify_client_id())


def signed_in() -> bool:
    return TOKEN_FILE.exists()


def _save_token(data: dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(TOKEN_FILE.read_text()) if TOKEN_FILE.exists() else {}
    token = {"access_token": data["access_token"],
             "refresh_token": data.get("refresh_token") or old.get("refresh_token"),
             "expires_at": time.time() + int(data.get("expires_in", 3600)) - 60}
    TOKEN_FILE.write_text(json.dumps(token))


def _token_request(fields: dict) -> dict:
    req = urllib.request.Request("https://accounts.spotify.com/api/token",
                                 data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SpotifyError(f"Spotify sign-in failed: {e.read().decode(errors='replace')[:200]}", e.code) from None


def sign_in(say=print, open_url=None) -> bool:
    """Open Chrome on Spotify's 'Agree' page and wait for the answer on 127.0.0.1:8765."""
    client_id = config.spotify_client_id()
    if not client_id:
        say("OTTO_SPOTIFY_CLIENT_ID isn't in your .env yet.")
        return False
    verifier = secrets.token_urlsafe(64)[:100]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT, "scope": SCOPES,
        "code_challenge_method": "S256", "code_challenge": challenge, "state": state})
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                result.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            ok = "code" in result
            self.wfile.write((f"<h2>{'Otto is connected to Spotify. You can close this tab.' if ok else 'Spotify sign-in was cancelled.'}</h2>").encode())

    server = http.server.HTTPServer(("127.0.0.1", 8765), Handler)
    server.timeout = 1
    say("Opening Spotify's sign-in page in Chrome. Click 'Agree'...")
    if open_url:
        open_url(url)
    else:
        import webbrowser
        webbrowser.open(url)
    deadline = time.time() + 180
    while "code" not in result and "error" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if "code" not in result:
        say("Spotify sign-in didn't finish (cancelled or timed out).")
        return False
    _save_token(_token_request({"grant_type": "authorization_code", "code": result["code"],
                                "redirect_uri": REDIRECT, "client_id": client_id, "code_verifier": verifier}))
    say("Spotify connected.")
    return True


def _access_token() -> str:
    if not TOKEN_FILE.exists():
        raise SpotifyError("not_signed_in")
    token = json.loads(TOKEN_FILE.read_text())
    if time.time() >= token.get("expires_at", 0):
        data = _token_request({"grant_type": "refresh_token", "refresh_token": token["refresh_token"],
                               "client_id": config.spotify_client_id()})
        _save_token(data)
        token = json.loads(TOKEN_FILE.read_text())
    return token["access_token"]


# ---------------------------------------------------------------------------------------------
# Web API
# ---------------------------------------------------------------------------------------------

def _call(method: str, path: str, params: dict | None = None, body: dict | None = None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else (b"" if method in ("PUT", "POST") else None)
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {_access_token()}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            msg = json.loads(raw).get("error", {}).get("message", raw)
        except Exception:
            msg = raw
        if e.code == 403 and "premium" in str(msg).lower():
            msg = "Spotify says this needs Premium."
        raise SpotifyError(str(msg)[:200], e.code) from None
    except urllib.error.URLError as e:
        raise SpotifyError(f"can't reach Spotify ({e.reason})") from None


def devices() -> list[dict]:
    return (_call("GET", "/me/player/devices") or {}).get("devices", [])


def _pick_device() -> dict | None:
    devs = devices()
    if not devs:
        return None
    pc = os.environ.get("COMPUTERNAME", "").lower()
    for d in devs:
        if d.get("is_active"):
            return d
    for d in devs:
        if d.get("type") == "Computer" and (not pc or pc in d.get("name", "").lower()):
            return d
    computers = [d for d in devs if d.get("type") == "Computer"]
    return computers[0] if computers else devs[0]


def ensure_device(launch) -> dict | None:
    """Make sure the Spotify app on this PC is available as a player (opens it if needed)."""
    d = _pick_device()
    if d:
        return d
    launch()
    for _ in range(20):          # up to ~10 s for the app to start and register
        time.sleep(0.5)
        d = _pick_device()
        if d:
            return d
    return None


def search(query: str, kinds: str = "track,artist,album,playlist", limit: int = 5) -> dict:
    return _call("GET", "/search", {"q": query, "type": kinds, "limit": limit}) or {}


def best_match(query: str, kind: str = "auto", artist: str = "") -> tuple[str, str, dict] | None:
    """Returns (kind, uri, item) for the best thing to play."""
    from rapidfuzz import fuzz

    if kind in ("track", "auto") and artist:
        res = search(f"track:{query} artist:{artist}", "track")
        items = (res.get("tracks") or {}).get("items") or []
        if not items:
            items = (search(f"{query} {artist}", "track").get("tracks") or {}).get("items") or []
        return ("track", items[0]["uri"], items[0]) if items else None
    if kind == "playlist":   # your own playlists first
        try:
            mine = (_call("GET", "/me/playlists", {"limit": 50}) or {}).get("items") or []
            scored = [(fuzz.WRatio(query.lower(), (p or {}).get("name", "").lower()), p) for p in mine if p]
            if scored:
                score, p = max(scored, key=lambda x: x[0])
                if score >= 80:
                    return "playlist", p["uri"], p
        except SpotifyError:
            pass
    types = {"auto": "track,artist,album,playlist", "song": "track"}.get(kind, kind)
    res = search(query, types)
    cand = []
    for k in ("artist", "playlist", "album", "track"):
        for i, it in enumerate(((res.get(k + "s") or {}).get("items") or [])[:5]):
            if not it:
                continue
            score = fuzz.ratio(query.lower(), it.get("name", "").lower()) - i * 3
            if kind == "auto":   # a song is the usual intent unless the name clearly fits better
                score += {"track": 6, "artist": 4, "album": 0, "playlist": -4}[k]
            cand.append((score, k, it))
    if not cand:
        return None
    _, k, it = max(cand, key=lambda c: c[0])
    return k, it["uri"], it


def describe(kind: str, item: dict) -> str:
    if kind == "track":
        return f"{item['name']} by {', '.join(a['name'] for a in item.get('artists', [])[:2])}"
    if kind == "album":
        return f"the album {item['name']}"
    if kind == "playlist":
        return f"the playlist {item['name']}"
    return item.get("name", "that")


def play(uri: str, kind: str, device_id: str) -> None:
    body = {"uris": [uri]} if kind == "track" else {"context_uri": uri}
    _call("PUT", "/me/player/play", {"device_id": device_id}, body)


def play_liked(device_id: str) -> None:
    me = _call("GET", "/me") or {}
    try:
        _call("PUT", "/me/player/play", {"device_id": device_id},
              {"context_uri": f"spotify:user:{me.get('id')}:collection"})
    except SpotifyError:
        saved = (_call("GET", "/me/tracks", {"limit": 50}) or {}).get("items", [])
        uris = [s["track"]["uri"] for s in saved if s.get("track")]
        if not uris:
            raise SpotifyError("Your Liked Songs is empty.")
        _call("PUT", "/me/player/play", {"device_id": device_id}, {"uris": uris})
    try:
        _call("PUT", "/me/player/shuffle", {"state": "true", "device_id": device_id})
    except SpotifyError:
        pass


def now_playing() -> dict | None:
    data = _call("GET", "/me/player/currently-playing")
    if not data or not data.get("item"):
        return None
    it = data["item"]
    return {"title": it.get("name"), "artist": ", ".join(a["name"] for a in it.get("artists", [])[:2]),
            "playing": data.get("is_playing", False)}


def control(what: str, device_id: str | None = None) -> None:
    p = {"device_id": device_id} if device_id else None
    if what == "pause":
        _call("PUT", "/me/player/pause", p)
    elif what == "resume":
        _call("PUT", "/me/player/play", p)
    elif what == "next":
        _call("POST", "/me/player/next", p)
    elif what == "previous":
        _call("POST", "/me/player/previous", p)


def is_playing() -> bool | None:
    try:
        state = _call("GET", "/me/player")
        return bool(state and state.get("is_playing"))
    except SpotifyError:
        return None


def sign_in_in_background_hint() -> str:
    return "Spotify isn't connected yet. Run  otto spotify  once to sign in."


