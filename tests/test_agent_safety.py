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


READ = {"tool": "read_window", "args": {}, "ok": True}


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
    ctx = make("discord.exe", "Discord", "Message @John", [READ, typed("hi")])
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



# ---- review fixes: judge the live screen, not what was read earlier ---------------------------

def _live(monkeypatch, exe, title, focused):
    from core import agent_safety
    from hands import win
    monkeypatch.setattr(win, "foreground", lambda: 77)
    monkeypatch.setattr(win, "window_info", lambda hwnd: {"exe": exe, "title": title, "rect": (0, 0, 100, 100)})
    monkeypatch.setattr(agent_safety, "focused_name", lambda: focused)


def test_safety_reads_the_live_window_not_the_last_one_read(monkeypatch):
    from core import tools
    from core.agent_safety import check
    _live(monkeypatch, "discord.exe", "#general - Discord", "Message @John")
    ctx = tools.ToolContext(dry_run=False, hwnd=5, app="Notepad")         # Notepad was read earlier
    ctx.controls = [{"id": 1, "name": "Text editor", "type": "Document", "focused": True}]
    ctx.history = [typed("hi john")]
    assert check("keys", {"keys": "enter"}, ctx)


def test_enter_on_a_focused_order_button_asks(monkeypatch):
    from core import tools
    from core.agent_safety import check
    _live(monkeypatch, "chrome.exe", "Checkout - Amazon", "Place your order")
    q = check("keys", {"keys": "enter"}, tools.ToolContext(dry_run=False))
    assert q and "Place your order" in q
    assert check("keys", {"keys": "space"}, tools.ToolContext(dry_run=False))


def test_open_forgets_the_last_window(monkeypatch):
    from core import tools
    from hands import registry
    registry.load_all()
    ctx = tools.ToolContext(dry_run=True, hwnd=5, controls=[{"id": 1, "name": "x", "rect": (0, 0, 1, 1)}])
    tools.call("open", {"what": "discord"}, ctx)
    assert ctx.hwnd is None and ctx.controls == []


def test_controls_must_be_read_again_after_a_click(monkeypatch):
    from core import tools
    from hands import indicator, ui_probe
    monkeypatch.setattr(ui_probe, "press", lambda c: True)
    monkeypatch.setattr(indicator, "point", lambda rect: None)
    from core import agent_safety
    monkeypatch.setattr(agent_safety, "front", lambda ctx: {"exe": "notepad.exe", "title": "Notepad", "focused": ""})
    ctx = tools.ToolContext(dry_run=False, controls=[{"id": 1, "name": "View", "type": "MenuItem", "rect": (0, 0, 9, 9)}])
    assert tools.call("click", {"control": 1}, ctx).ok
    assert not tools.call("click", {"control": 1}, ctx).ok      # numbers are stale now


def test_mouse_fallback_checks_what_is_under_the_point(monkeypatch):
    from core import agent_safety, tools
    from hands import indicator, mouse, ui_probe
    clicked = []
    monkeypatch.setattr(ui_probe, "press", lambda c: False)
    monkeypatch.setattr(indicator, "point", lambda rect: None)
    monkeypatch.setattr(mouse, "click_at", lambda *a, **k: clicked.append(a))
    monkeypatch.setattr(agent_safety, "name_at", lambda x, y: "Place order")
    ctx = tools.ToolContext(dry_run=False, controls=[{"id": 1, "name": "Basket", "type": "Button", "rect": (0, 0, 9, 9)}])
    r = tools.call("click", {"control": 1}, ctx)
    assert r.asks and not clicked


def test_unknown_point_lookup_failure_asks(monkeypatch):
    from core import agent_safety, tools
    monkeypatch.setattr(agent_safety, "name_at", lambda x, y: None)
    c = tools.ToolContext(why="open the video")
    c.look = {"region": (0, 0, 1280, 720), "scale": 1.0}
    assert agent_safety.check("click", {"x": 10, "y": 10}, c)


def test_open_programs_by_any_path_shape_asks():
    from core import tools
    from hands import registry
    registry.load_all()
    for what in ("C:/Downloads/setup.exe", "C:\\Downloads\\setup.exe", "file:///C:/Downloads/setup.exe"):
        r = tools.call("open", {"what": what}, tools.ToolContext(dry_run=True))
        assert r.asks, what
    r = tools.call("open", {"what": "javascript:alert(1)"}, tools.ToolContext(dry_run=True))
    assert not r.ok and not r.asks


def test_type_never_replaces_existing_text(monkeypatch):
    from core import tools
    from hands import apps, ui_probe, win
    box = {"id": 1, "name": "Text editor", "type": "Document", "rect": (0, 0, 9, 9), "element": None}
    replaced, typed_keys = [], []
    monkeypatch.setattr(ui_probe, "read_text", lambda c: "line 1\nline 2")
    monkeypatch.setattr(ui_probe, "set_value", lambda c, t: replaced.append(t) or True)
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    monkeypatch.setattr(apps, "type_text", lambda t: typed_keys.append(t))
    from core import agent_safety
    monkeypatch.setattr(agent_safety, "front", lambda ctx: {"exe": "notepad.exe", "title": "Notepad", "focused": ""})
    ctx = tools.ToolContext(dry_run=False, controls=[box])
    tools.call("type", {"text": ")", "control": 1}, ctx)
    assert not replaced and typed_keys == [")"]
