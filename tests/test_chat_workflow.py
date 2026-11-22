from types import SimpleNamespace

import pytest
from core import reading
from hands import app_control, ui_probe, win, web
from tests.test_pipeline import otto


def test_whatsapp_filtered_rows_exclude_message_search_hits(monkeypatch):
    def element(id_, name, value="", role="row"):
        return SimpleNamespace(GetRuntimeId=lambda: [id_], CurrentName=name, CurrentAriaRole=role,
                               CurrentIsOffscreen=False, value=value)
    doc, grid = element(1, ""), element(2, "Search results.")
    contact = element(4, "date ideas Yesterday", "date ideas\nYesterday")
    rows = [element(3, "Chats"), contact, contact, element(5, "Messages"),
            element(6, "date ideas Yesterday", "date ideas\nYesterday")]
    def elements(hwnd, kinds, parent=None):
        return {"Document": [doc, doc], "DataGrid": [grid], "DataItem": rows}[kinds[0]]
    monkeypatch.setattr(ui_probe, "reading_elements", elements)
    monkeypatch.setattr(ui_probe, "_pattern", lambda *args: SimpleNamespace(
        RangeFromChild=lambda row: SimpleNamespace(GetText=lambda limit: row.value)))
    assert ui_probe.whatsapp_rows(1, sidebar=True) == [(contact, "date ideas\nYesterday")]


def test_group_name_is_carried_through_summary_offer_and_dictation(otto):
    result = otto.handle('can you find "date ideas" group chat and reply to it?')
    assert "date ideas" in result.text and otto.pending.kind == "offer_chat_reply"
    assert "Want to reply?" in otto.handle("what are they talking about?").text
    assert "What would you like to say" in otto.handle("yes").text
    reply = otto.handle("Saturday works")
    assert otto.pending.kind == "confirm_plan" and "Saturday works" in reply.text
    assert otto.pending.plan.steps[0]["with"]["to"] == "date ideas"


def test_search_field_request_passes_registry_validation(otto):
    otto.handle("type in the search bar, how to train your dragon")
    assert otto.trace["outcome_status"] == "simulated"


def test_literal_send_uses_the_verified_recipient(otto, monkeypatch):
    otto.handle('find "date ideas" group chat')
    otto.handle("yes")
    calls = []
    monkeypatch.setattr(otto, "_run", lambda plan, intent, t, confirmed=False:
                        calls.append((plan.steps, confirmed)) or SimpleNamespace(text="done", details="", speak=""))
    otto.handle("Saturday works and send it")
    steps, approved = calls[-1]
    assert approved and [s["do"] for s in steps] == ["draft_whatsapp", "send_typed"]
    assert steps[-1]["with"] == {"text": "Saturday works", "to": "date ideas", "app": "WhatsApp"}


@pytest.mark.parametrize("kind,label,address", [("search", "Address and search bar", "https://www.google.com/"),
                                               ("draft", "Ask Gemini", "https://gemini.google.com/app")])
def test_edit_replaces_contents_without_keys(monkeypatch, kind, label, address):
    box = dict(type="Edit", enabled=True, name=label, element=SimpleNamespace(CurrentName=label, SetFocus=lambda: None))
    contents = [address]
    monkeypatch.setattr(app_control, "_current_window", lambda: ({"hwnd": 1, "exe": "chrome.exe"}, "Chrome"))
    monkeypatch.setattr(ui_probe, "list_controls", lambda hwnd, limit: [box])
    monkeypatch.setattr(ui_probe, "set_value", lambda c, text: contents.append(text) or True)
    monkeypatch.setattr(ui_probe, "read_text", lambda c: contents[-1])
    monkeypatch.setattr(app_control, "_same_box", lambda element: True)
    monkeypatch.setattr(win, "foreground", lambda: 1)
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    monkeypatch.setattr(web, "chrome_addresses", lambda only: [address])
    monkeypatch.setattr(web, "is_browser_address_field", lambda element: True)
    assert app_control.edit_input(kind, "how to train your dragon").ok
    assert contents[-1] == "how to train your dragon"
