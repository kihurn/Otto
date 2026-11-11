"""Safety rules for the agent's tool calls (agent core plan, task 4)."""

import pytest


@pytest.fixture
def make(monkeypatch):
    from core import agent_safety, tools

    def build(exe="notepad.exe", title="Untitled - Notepad", focused="Text editor", history=(), controls=()):
        monkeypatch.setattr(agent_safety, "front", lambda ctx: {"exe": exe, "title": title, "focused": focused})
        ctx = tools.ToolContext(dry_run=False)
        ctx.history = list(history)
        ctx.controls = list(controls)
        return ctx
    return build


def typed(text):
    return {"tool": "type", "args": {"text": text}, "ok": True}


def test_enter_in_discord_asks(make):
    from core.agent_safety import check
    ctx = make("discord.exe", "#general - Discord", "Message @John", [typed("ok sure, see you soon")])
    q = check("keys", {"keys": "enter"}, ctx)
    assert q and "send" in q.lower() and "ok sure, see you soon" in q


def test_ctrl_enter_in_gmail_asks(make):
    from core.agent_safety import check
    assert check("keys", {"keys": "ctrl+enter"}, make("chrome.exe", "Inbox - Gmail - Google Chrome", "Message Body"))


def test_enter_in_word_is_free(make):
    from core.agent_safety import check
    assert check("keys", {"keys": "enter"}, make("WINWORD.EXE", "Document1 - Word", "Page 1")) is None


def test_enter_after_typing_in_powershell_asks_with_command(make):
    from core.agent_safety import check
    ctx = make("WindowsTerminal.exe", "Windows PowerShell", "", [typed("pip install requests")])
    q = check("keys", {"keys": "enter"}, ctx)
    assert q and "pip install requests" in q


def test_enter_in_run_box_asks(make):
    from core.agent_safety import check
    assert check("keys", {"keys": "enter"}, make("explorer.exe", "Run", "Open:", [typed("cmd")]))


def test_typing_a_newline_into_a_chat_counts_as_send(make):
    from core.agent_safety import check
    assert check("type", {"text": "hi\n"}, make("discord.exe", "Discord", "Message @John"))


def test_select_all_then_delete_asks(make):
    from core.agent_safety import check
    ctx = make("WINWORD.EXE", "Document1 - Word", "Page 1", [{"tool": "keys", "args": {"keys": "ctrl+a"}, "ok": True}])
    assert check("keys", {"keys": "delete"}, ctx)
    assert check("keys", {"keys": "backspace"}, ctx)


def test_delete_in_explorer_asks(make):
    from core.agent_safety import check
    assert check("keys", {"keys": "delete"}, make("explorer.exe", "Downloads - File Explorer", "Items View"))
    assert check("keys", {"keys": "shift+delete"}, make("explorer.exe", "Downloads - File Explorer", "Items View"))


def test_backspace_in_textbox_free(make):
    from core.agent_safety import check
    assert check("keys", {"keys": "backspace"}, make()) is None


def test_click_named_buy_asks(make):
    from core.agent_safety import check
    ctx = make("chrome.exe", "Cart - Amazon", "", controls=[{"id": 4, "name": "Buy now", "type": "Button"}])
    q = check("click", {"control": 4}, ctx)
    assert q and "Buy now" in q


def test_click_run_in_run_box_asks(make):
    from core.agent_safety import check
    ctx = make("explorer.exe", "Run", "Open:", [typed("cmd")], controls=[{"id": 2, "name": "OK", "type": "Button"}])
    assert check("click", {"control": 2}, ctx)


def test_plain_click_free(make):
    from core.agent_safety import check
    ctx = make(controls=[{"id": 1, "name": "View", "type": "MenuItem"}])
    assert check("click", {"control": 1}, ctx) is None


def test_yes_lets_exactly_that_call_through(make):
    from core.agent_safety import check
    ctx = make("discord.exe", "Discord", "Message @John", [typed("hi")])
    ctx.confirmed = True
    assert check("keys", {"keys": "enter"}, ctx) is None


def test_type_into_password_refused_even_confirmed(make):
    from core import tools
    ctx = make(controls=[{"id": 1, "name": "Password", "type": "Edit", "password": True}])
    ctx.confirmed = True
    r = tools.call("type", {"text": "secret", "control": 1}, ctx)
    assert not r.ok and "password" in r.say.lower()


def test_tools_call_runs_the_safety_check_first(make, monkeypatch):
    from core import tools
    from hands import win
    pressed = []
    monkeypatch.setattr(win, "hotkey", lambda keys: pressed.append(keys))
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    ctx = make("discord.exe", "Discord", "Message @John", [typed("hi")])
    r = tools.call("keys", {"keys": "enter"}, ctx)
    assert r.asks and not pressed
    ctx.confirmed = True
    assert tools.call("keys", {"keys": "enter"}, ctx).ok and pressed == ["enter"]


def test_plain_close_does_not_ask(make):
    from core import tools
    from hands import registry
    registry.load_all()
    ctx = make()
    ctx.dry_run = True
    r = tools.call("close", {"app": "Word"}, ctx)
    assert r.ok and not r.asks
