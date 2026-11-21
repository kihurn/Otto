from types import SimpleNamespace

import pytest

from core import dictation
from hands import app_control, apps, ui_probe, win
from hands.registry import Result
from tests.test_pipeline import otto


@pytest.fixture
def chat(monkeypatch):
    state = SimpleNamespace(front=1, focused=None, content="", writes=[], name="Type a message to Hayley")
    element = SimpleNamespace(CurrentName=state.name)
    element.SetFocus = lambda: setattr(state, "focused", element)
    box = dict(type="Edit", enabled=True, name=state.name, element=element)
    monkeypatch.setattr(win, "find_window", lambda app: {"hwnd": 2, "exe": "WhatsApp.Root.exe"})
    monkeypatch.setattr(win, "foreground", lambda: state.front)
    monkeypatch.setattr(win, "focus", lambda hwnd: setattr(state, "front", hwnd) or True)
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    monkeypatch.setattr(ui_probe, "list_controls", lambda hwnd, limit: [dict(box, name="Search"), box])
    monkeypatch.setattr(app_control, "_same_box", lambda el: el is state.focused)
    monkeypatch.setattr(ui_probe, "read_text", lambda box: state.content)
    monkeypatch.setattr(ui_probe, "set_value", lambda box, text: False)
    monkeypatch.setattr(app_control, "chat_text", lambda hwnd: "Hayley: Any news?")
    def write(text):
        assert state.front == 2 and state.focused is element
        state.writes.append(text)
        state.content = text
        return Result(True, "Typed.")
    monkeypatch.setattr(apps, "type_text", write)
    monkeypatch.setattr(dictation, "draft_reply", lambda *args: ("Next semester.", "fake"))
    monkeypatch.setattr(win, "hotkey", lambda key: pytest.fail("Unexpected keypress"))
    monkeypatch.setattr(app_control, "LAST_TYPED", {})
    return state


def test_named_reply_and_check_again_use_same_box(otto, chat):
    otto.dry_run = False
    reply = otto.handle("can you look at my whatsapp and reply to Hayley?")
    assert "Just checking" in reply.text and "Hayley" in reply.text
    assert chat.writes == ["Next semester."]
    otto.handle("no")
    assert chat.content == "Next semester."
    assert "draft is in Hayley" in otto.handle("please check again").text
    chat.content = ""
    assert "box is empty" in otto.handle("you did not write anything").text
    reply = otto.handle("you did not write anything yet, can you reply to her saying that Minn confirmed?")
    assert "Just checking" in reply.text and chat.writes == ["Next semester."] * 2


@pytest.mark.parametrize("existing", [None, "My unfinished reply"])
def test_unreadable_or_existing_draft_is_preserved(otto, chat, existing):
    otto.dry_run = False
    chat.content = existing
    reply = otto.handle("reply to Hayley in WhatsApp saying next semester")
    assert "Next semester." in reply.text and not otto.pending
    assert not chat.writes and chat.content == existing


def test_wrong_recipient_is_never_typed(chat):
    assert not app_control.draft_whatsapp("Hay", "Next semester.").ok
    assert not chat.writes


def test_whatsapp_window_ignores_a_chrome_tab_named_whatsapp(monkeypatch):
    browser = {"title": "WhatsApp", "exe": "chrome.exe"}
    app = {"title": "WhatsApp", "exe": "WhatsApp.Root.exe"}
    monkeypatch.setattr(win, "windows", lambda: [browser, app])
    assert win.find_window("WhatsApp") is app


def test_delayed_readback_does_not_type_twice(chat, monkeypatch):
    values = iter(["", "", "", "", "Next semester."])
    monkeypatch.setattr(ui_probe, "read_text", lambda box: next(values))
    assert app_control.draft_whatsapp("Hayley", "Next semester.").ok
    assert chat.writes == ["Next semester."]


def test_direct_write_waits_without_keyboard_retry(chat, monkeypatch):
    monkeypatch.setattr(ui_probe, "set_value", lambda box, text: True)
    monkeypatch.setattr(app_control.time, "sleep", lambda seconds: None)
    assert not app_control.draft_whatsapp("Hayley", "Next semester.").ok
    assert chat.writes == []
