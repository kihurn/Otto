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


def test_named_group_word_order(otto):
    reply = otto.handle("in whatsapp, can you find the group chat called date ideas and reply to it?")
    assert "date ideas" in reply.text and otto.pending.text == "date ideas"


def test_unread_choice_is_bound_before_reading(otto, monkeypatch):
    from core.pipeline import Reply
    otto.dry_run = False
    names = ["Yusri", "Hayley"]
    monkeypatch.setattr(app_control, "unread_chats", lambda: names)
    summary = []
    run = otto._run
    monkeypatch.setattr(otto, "_run", lambda plan, *args: run(plan, *args)
                        if plan.steps[0]["do"] == "list_unread_chats" else
                        otto.trace.update(outcome_status="needs_input") or Reply("Wrong chat"))
    monkeypatch.setattr(otto, "_chat_summary", lambda *args: summary.append(args))
    assert "Yusri" in otto.handle("do i have any incoming messages?").text
    assert "Which unread chat?" in otto.handle("can you open that and summarize what is it saying").text
    assert otto.handle("Yusri").text == "Wrong chat"
    assert not summary
    names.pop()
    otto.handle("do i have any incoming messages?")
    assert otto.handle("can you open that and summarize what is it saying").text == "Wrong chat"


def test_targeted_summary_excludes_self_other_people_and_quotes(monkeypatch):
    rows = [(1, "You:\nI want a 5060"), (2, "Yusri:\nWhat is your budget?"),
            (3, "Gabriel:\nBuy a GPU"), (4, "Yusri:\nGabriel: Buy a GPU\nOK")]
    monkeypatch.setattr(ui_probe, "whatsapp_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(ui_probe, "reading_elements", lambda hwnd, types, parent:
                        [SimpleNamespace(CurrentName="Quoted message")] if parent == 4 else [])
    text, coverage = reading.attributed_messages(8, "yusri")
    assert text == "Yusri (incoming): What is your budget?" and "1 quoted" in coverage
    assert "You (outgoing)" in reading.attributed_messages(8)[0]


def test_reply_to_him_after_manual_switch_stops(otto, monkeypatch):
    from core import details
    import time
    request = "can you reply to him saying that yea 2026 is fucked with the gpu prices"
    assert details.reply_request(request)["who"] == ""
    otto.dry_run = False
    otto.whatsapp_draft = ("Yusri", "", time.monotonic())
    monkeypatch.setattr(app_control, "whatsapp_box", lambda who: (1, None))
    monkeypatch.setattr(otto, "_whatsapp_reply", lambda *a: pytest.fail("Wrong conversation"))
    assert "still the open conversation" in otto.handle(request).text


def test_unread_from_self_chat_then_question_and_pronoun_reply(otto, monkeypatch):
    from core.pipeline import Reply
    active = ["@kihurn"]
    otto.dry_run = False
    monkeypatch.setattr(app_control, "unread_chats", lambda: ["Yusri"])
    original_run = otto._run
    def run(plan, intent, request):
        step, = plan.steps
        if step["do"] == "list_unread_chats":
            return original_run(plan, intent, request)
        assert step == {"do": "find_chat", "with": {"to": "Yusri"}}
        active[0] = "Yusri"
        otto.trace["outcome_status"] = "verified"
        return Reply("Opened Yusri.")
    monkeypatch.setattr(otto, "_run", run)
    monkeypatch.setattr(app_control, "whatsapp_box", lambda who:
                        (42, {"name": "Type a message to Yusri"} if active[0] == who else None))
    speakers = []
    def read(hwnd, speaker):
        assert hwnd == 42 and active == ["Yusri"]
        speakers.append(speaker)
        return "Yusri (incoming): Which card did you buy?", "1 attributed visible message"
    monkeypatch.setattr(reading, "attributed_messages", read)
    monkeypatch.setattr(reading, "summarize", lambda text, prompt, brain: "He asks which card you bought.")
    assert "Yusri" in otto.handle("do i have any incoming messages?").text and active == ["@kihurn"]
    assert "Yusri" in otto.handle("can you open that and summarize what is it saying").text
    assert "which card" in otto.handle("ok what does yusri want then?").text
    assert speakers == ["", "yusri"]
    monkeypatch.setattr(otto, "_whatsapp_reply", lambda request, who, words: Reply(f"{who}: {words}"))
    assert otto.handle("can you reply to him saying that prices are high").text == "Yusri: prices are high"


def test_group_sender_button_without_colon(monkeypatch):
    def el(i, role, name):
        return SimpleNamespace(GetRuntimeId=lambda: (i,), CurrentAriaRole=role, CurrentName=name,
                               CurrentIsOffscreen=False)
    doc, grid, row = el(1, "document", ""), el(2, "grid", "Chat list"), el(3, "row", "")
    def elements(hwnd, kinds, parent=None):
        if kinds == ("DataItem",):
            return [row] if parent is doc else []
        return {"Document": [doc], "DataGrid": [grid], "Group": [el(4, "button", "Gabriel")]}[kinds[0]]
    monkeypatch.setattr(ui_probe, "reading_elements", elements)
    monkeypatch.setattr(ui_probe, "_pattern", lambda *args: SimpleNamespace(
        RangeFromChild=lambda e: SimpleNamespace(GetText=lambda n: "Gabriel\nWho's coming?\n8:14 pm")))
    assert ui_probe.whatsapp_rows(1, sidebar=False)[0][1].startswith("Gabriel:\nWho's coming?")


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
