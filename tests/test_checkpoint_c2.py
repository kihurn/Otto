"""Codex checkpoint C2 (20 Nov): Enter after typing in Claude went through unasked, and "I've sent that message"
passed; the YouTube key could follow a redirect; background windows that weren't Otto's could be hidden."""
import pytest
from tests.test_pipeline import otto  # noqa: F401  (the fake-Laya, fake-brain Otto)

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


# ---- part 2: items 5-10 ----------------------------------------------------------------------------------

def test_while_you_keep_typing_otto_doesnt_take_the_screen(monkeypatch):
    from hands import win, youtube
    from tests.test_background import FakeDesktop
    FakeDesktop(monkeypatch, {1: "code.exe"}, front=1)
    monkeypatch.setattr(win, "wait_for_pause", lambda: False)
    monkeypatch.setenv("OTTO_YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(youtube, "find_video", lambda q, n=1: ("abc", "Lofi girl"))
    opened = []
    from hands import web
    monkeypatch.setattr(web, "open_in_browser", lambda *a, **k: opened.append(a))
    result = youtube.play_video("lofi")
    assert not result.ok and "busy with the keyboard or mouse" in result.say and opened == []


def test_an_existing_window_otto_brought_forward_gives_yours_back(monkeypatch):
    from hands import win
    from tests.test_background import FakeDesktop
    pc = FakeDesktop(monkeypatch, {1: "code.exe", 2: "spotify.exe"}, front=1)
    monkeypatch.setattr(win, "window_info", lambda h: {"exe": pc.windows[h]})
    with win.screen_borrowed("spotify.exe"):
        pc.front = 2                                   # open_app focused the Spotify that was already open
    assert pc.minimised == [] and pc.focused == [1]


def test_settings_saved_with_a_bom_still_load(tmp_path, monkeypatch):
    from core import config
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"show_details": false}')
    monkeypatch.setattr(config, "SETTINGS_FILE", path)
    assert config.load_settings()["show_details"] is False


def test_a_filler_in_front_of_the_time_needs_no_model(otto):
    reply = otto.handle("Ummmmmm, what's the time?")
    assert otto.trace.get("answer_by") == "local" and reply.text
    otto.handle("um, what's the time in Tokyo")
    assert otto.trace.get("answer_by") != "local"


def test_thanks_heard_unclearly_gets_a_reply_not_a_question(otto):
    assert otto.handle("Thank you", heard_conf=-0.91).text == "You're welcome."


def test_no_i_did_not_ends_did_you_say(otto):
    assert otto.handle("and cloud.", heard_conf=-1.08).text == 'Sorry, did you say "and cloud."?'
    assert otto.handle("No I did not", heard_conf=-0.45).text == "Okay, never mind."
    assert otto.pending is None


def test_mhm_answers_a_harmless_question_but_never_approves(otto):
    import time
    from core.pipeline import Pending
    otto.pending = Pending("agent_confirm", expires=time.time() + 60, text="send it", agent={"options": []})
    assert otto.handle("mhm").text == "" and otto.pending.kind == "agent_confirm"     # ignored, still waiting
    otto.pending = None


# ---- review of parts 1-2 before sending ---------------------------------------------------------------------

def test_vs_code_and_failed_typing_and_pastes_still_ask(monkeypatch):
    place(monkeypatch, "code.exe", "")                  # VS Code: terminal and chat panel, so not "harmless"
    c = tools.ToolContext(dry_run=False)
    c.history.append({"tool": "type", "args": {"text": "hi"}, "ok": False})     # the keys went out anyway
    assert agent_safety.check("keys", {"keys": "enter"}, c).startswith("send")
    place(monkeypatch, "someapp.exe", "")
    c = tools.ToolContext(dry_run=False)
    c.history.append({"tool": "keys", "args": {"keys": "ctrl+v"}, "ok": True})
    assert agent_safety.check("keys", {"keys": "enter"}, c).startswith("send")


def test_describing_someone_elses_message_is_not_a_claim():
    from core.agent import _unbacked_claim
    reads = [{"tool": "read_window", "args": {}, "ok": True}]
    assert _unbacked_claim("The last message was sent by Ellee.", reads, "what's on my discord") == ""


def test_thanks_with_a_question_waiting_goes_to_the_question(otto):
    import time
    from core.pipeline import Pending
    otto.pending = Pending("heard", expires=time.time() + 60, text="play lofi")
    assert otto.handle("thank you", heard_conf=-0.95).text != "You're welcome."
    otto.pending = None


def test_an_already_open_terminal_gets_one_look(monkeypatch):
    from hands import apps, win
    monkeypatch.setattr(win, "IS_WINDOWS", True)
    monkeypatch.setattr(apps, "_resolve", lambda app: ({"name": "Windows PowerShell"}, None))
    monkeypatch.setattr(win, "find_window", lambda name: {"hwnd": 5, "exe": "powershell.exe"})
    monkeypatch.setattr(win, "focus", lambda hwnd: True)
    looks = []
    monkeypatch.setattr(apps, "_terminal_text", lambda hwnd: looks.append(hwnd) or "Copying files 40%")
    result = apps.open_app("powershell")
    assert looks == [5] and result.say.endswith("but it may be busy: its prompt isn't showing yet.")


# ---- 21 Nov live runs (WhatsApp) ------------------------------------------------------------------------------

def test_an_unnamed_button_in_a_chat_gets_the_send_question(ctx, monkeypatch):
    place(monkeypatch, "whatsapp.exe", "", "WhatsApp")
    assert agent_safety.check("click", {"control": 38}, ctx).startswith("send")


def test_the_message_task_wont_start_on_leftover_text(monkeypatch):
    from core import live_test
    box = {"name": "Type a message", "type": "Edit"}
    monkeypatch.setattr(live_test, "chat_boxes", lambda app: [(box, "otto live 3445")])
    assert "isn't empty" in live_test._message("WhatsApp").setup({})
    monkeypatch.setattr(live_test, "chat_boxes", lambda app: [(box, "")])
    assert live_test._message("WhatsApp").setup({}) is None
