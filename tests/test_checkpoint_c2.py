"""Codex checkpoint C2 (20 Nov): Enter after typing in Claude went through unasked, and "I've sent that message"
passed; the YouTube key could follow a redirect; background windows that weren't Otto's could be hidden."""
import pytest

from core import agent_safety, tools


@pytest.fixture
def ctx():
    from hands import registry
    registry.load_all()
    c = tools.ToolContext(dry_run=False)
    c.history.append({"tool": "type", "args": {"text": "everything works right now"}, "ok": True})
    return c


def place(monkeypatch, exe, focused="", title="Some App"):
    monkeypatch.setattr(agent_safety, "front", lambda ctx: {"hwnd": 9, "exe": exe, "title": title, "focused": focused})
    monkeypatch.setattr(agent_safety, "focused_text", lambda: None)


@pytest.mark.parametrize("exe, focused", [("claude.exe", ""), ("someapp.exe", ""), ("someapp.exe", "Write here"),
                                          ("chrome.exe", "")])
def test_enter_after_typing_asks_unless_the_place_is_known_harmless(ctx, monkeypatch, exe, focused):
    place(monkeypatch, exe, focused)
    assert agent_safety.check("keys", {"keys": "enter"}, ctx).startswith("send")
    assert agent_safety.check("keys", {"keys": "ctrl+enter"}, ctx).startswith("send")
    assert agent_safety.check("type", {"text": "hi\n"}, ctx).startswith("send")         # a typed new line too
    assert agent_safety.check("click", {"control": 1}, ctx) is not None                 # an unnamed button


@pytest.mark.parametrize("exe, focused", [("notepad.exe", ""), ("winword.exe", "Page 1"),
                                          ("chrome.exe", "Address and search bar"), ("chrome.exe", "Search")])
def test_enter_in_an_editor_or_a_search_box_just_happens(ctx, monkeypatch, exe, focused):
    place(monkeypatch, exe, focused)
    assert agent_safety.check("keys", {"keys": "enter"}, ctx) is None


def test_enter_without_typing_first_is_unchanged(monkeypatch):
    place(monkeypatch, "someapp.exe")
    assert agent_safety.check("keys", {"keys": "enter"}, tools.ToolContext(dry_run=False)) is None


def test_the_claude_trace_now_stops_at_the_question(monkeypatch):
    # "Can you type in Claude that everything works right now?" -> type, then Enter: must wait for a yes.
    from core import agent
    from tests.test_agent import Scripted, call
    place(monkeypatch, "claude.exe", "", "Claude")
    monkeypatch.setattr(agent_safety, "blocked", lambda name, args, ctx: None)
    ctx = tools.ToolContext(dry_run=False)
    ctx.history.append({"tool": "type", "args": {"text": "everything works right now"}, "ok": True})
    r = agent.run("can you type in claude that everything works right now", [],
                  Scripted(call("keys", keys="enter"), call("done", say="I've sent that message for you.")), ctx)
    assert r.status == "confirm" and r.say.startswith("send")


def test_a_sent_claim_needs_a_send_you_approved_whatever_the_request_said():
    from core.agent import _unbacked_claim
    typed = {"tool": "type", "args": {"text": "hi"}, "ok": True}
    unasked_enter = {"tool": "keys", "args": {"keys": "enter"}, "ok": True}
    approved_enter = dict(unasked_enter, approved=True)
    request = "can you type in claude that everything works right now"
    assert _unbacked_claim("I've sent that message for you.", [typed, unasked_enter], request) == "Nothing was sent."
    assert _unbacked_claim("Your message was sent.", [typed], request) == "Nothing was sent."
    assert _unbacked_claim("I've sent that message for you.", [typed, approved_enter], request) == ""
    assert _unbacked_claim("Ellee sent a clip earlier.", [], "what is on my discord") == ""   # not Otto's own claim


def test_two_new_windows_means_otto_touches_neither(monkeypatch):
    from hands import win
    from tests.test_background import FakeDesktop
    pc = FakeDesktop(monkeypatch, {1: "code.exe"}, front=1)
    with win.screen_borrowed("chrome.exe") as b:
        pc.opens(3, "chrome.exe")
        pc.opens(4, "chrome.exe")                    # you opened a Chrome window while the video loaded
    assert b.new == [] and pc.minimised == [] and pc.focused == []


def test_the_youtube_key_never_follows_a_redirect():
    import urllib.request
    from hands import youtube
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/search", headers={"X-Goog-Api-Key": "k"})
    assert youtube._NoRedirect().redirect_request(req, None, 302, "Found", {}, "https://evil.example/") is None
