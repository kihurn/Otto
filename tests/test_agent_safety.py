"""Safety rules for the agent's tool calls (agent core plan, task 4)."""

import pytest


@pytest.fixture
def make(monkeypatch):
    from core import agent_safety, tools

    def build(exe="notepad.exe", title="Untitled - Notepad", focused="Text editor", history=(), controls=()):
        monkeypatch.setattr(agent_safety, "front", lambda ctx: {"exe": exe, "title": title, "focused": focused})
        monkeypatch.setattr(agent_safety, "focused_text", lambda: None)     # never the real PC's focused box
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


def test_typing_a_newline_into_a_chat_is_refused_even_after_a_read(make):
    # Type and send in one step would let the question read the box before the new text (Codex re-review 20 Nov).
    from core import tools
    from core.agent_safety import blocked
    ctx = make("discord.exe", "Discord", "Message @John", [READ])
    assert "without a new line" in blocked("type", {"text": " Ki\n"}, ctx)
    r = tools.call("type", {"text": " Ki\n"}, ctx)
    assert not r.ok and not r.asks


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


# ---- checkpoint B review (Codex, 19 Nov): the gate ----------------------------------------------------

def test_a_shortcut_is_checked_exactly_as_it_is_pressed():
    from core import tools
    from hands import win
    assert win.parse_hotkey("Shift + Ctrl + Enter") == (("ctrl", "shift"), "enter")
    for bad in ("a+enter", "tab+enter", "space+delete", "ctrl+ctrl+s", "ctrl+", "ctrl+banana", "win+r"):
        assert tools.validate("keys", {"keys": bad}), bad          # refused before the gate even looks
    with pytest.raises(ValueError):
        win.hotkey("a+enter")                                       # and Windows refuses it too


@pytest.mark.parametrize("keys", ["alt+enter", "shift+ctrl+enter", "ctrl+shift+enter", "Enter"])
def test_any_enter_in_a_chat_asks(make, keys):
    from core.agent_safety import check
    ctx = make("discord.exe", "#general - Discord", "Message @John", [READ, typed("hi")])
    assert check("keys", {"keys": keys}, ctx)


def test_shift_delete_in_explorer_asks(make):
    from core.agent_safety import check
    assert check("keys", {"keys": "ctrl+shift+delete"}, make("explorer.exe", "Downloads", "Items View"))


def test_typing_refused_when_the_password_check_fails(make, monkeypatch):
    from core import tools
    from hands import apps, win
    typed_keys = []
    monkeypatch.setattr(win, "focused_is_password", lambda: None)          # Windows couldn't tell
    monkeypatch.setattr(apps, "type_text", lambda t: typed_keys.append(t))
    r = tools.call("type", {"text": "hello"}, make())
    assert not r.ok and "couldn't check" in r.say and not typed_keys


def test_a_command_otto_wrote_is_shown_and_never_run_without_a_yes(make, monkeypatch):
    # User decision 20 Nov: Otto may work out the command ("check my IP" -> ipconfig), but Enter always asks
    # with the exact command.
    from core import tools
    from hands import apps, win
    typed_keys, pressed = [], []
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    monkeypatch.setattr(apps, "type_text", lambda t: typed_keys.append(t))
    monkeypatch.setattr(win, "hotkey", lambda k: pressed.append(k))
    ctx = make("powershell.exe", "Windows PowerShell", "")
    ctx.request = "check my ip address"
    assert tools.call("type", {"text": "ipconfig /all"}, ctx).ok and typed_keys == ["ipconfig /all"]
    r = tools.call("keys", {"keys": "enter"}, ctx)
    assert r.asks == 'run "ipconfig /all" in Windows PowerShell' and not pressed


def test_close_that_leaves_the_app_open_ends_the_turn(make, monkeypatch):
    from core import tools
    from hands import win
    monkeypatch.setattr(win, "find_window", lambda app: {"hwnd": 5})
    monkeypatch.setattr(win, "exists", lambda hwnd: True)                  # still open: "save changes?"
    monkeypatch.setattr(tools, "CLOSE_WAIT", 0)
    monkeypatch.setattr(tools, "_action", lambda ctx, do, **w: tools.ToolResult(True, "Closing Notepad."))
    r = tools.call("close", {"app": "notepad"}, make())
    assert not r.ok and r.observed.get("end") == "done" and "left that to you" in r.say
    monkeypatch.setattr(win, "exists", lambda hwnd: False)
    assert tools.call("close", {"app": "notepad"}, make()).ok


def test_a_changed_draft_is_asked_about_again(monkeypatch):
    from core import agent, agent_safety, tools
    from tests.test_agent import Scripted, call
    from hands import win
    box = {"text": "see you at 5"}
    monkeypatch.setattr(agent_safety, "front", lambda c: {"hwnd": 3, "exe": "discord.exe", "title": "Discord",
                                                          "focused": "Message @John"})
    monkeypatch.setattr(agent_safety, "focused_text", lambda: box["text"])
    monkeypatch.setattr(agent_safety, "otto_in_front", lambda c: False)
    monkeypatch.setattr(win, "foreground", lambda: 3)
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    pressed = []
    monkeypatch.setattr(win, "hotkey", lambda k: pressed.append(k))
    ctx = tools.ToolContext(dry_run=False)
    brain = Scripted(call("read_window"), call("keys", keys="enter"))
    monkeypatch.setattr(tools.TOOLS["read_window"], "run", lambda c, app="": tools.ToolResult(True, "Read."))
    r = agent.run("send it", [], brain, ctx)
    assert r.status == "confirm" and "see you at 5" in r.say
    box["text"] = "see you at 5 and bring the money"                   # edited while the question was open
    r2 = agent.resume(r.pending, brain, yes=True)
    assert r2.status == "confirm" and "bring the money" in r2.say and not pressed
    brain.replies.append(call("done", say="Sent."))
    r3 = agent.resume(r2.pending, brain, yes=True)
    assert pressed == ["enter"] and r3.status == "done"


def test_terminal_commands_are_never_typed_key_by_key(make, monkeypatch):
    from core import tools
    from hands import apps, win
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    monkeypatch.setattr(apps, "type_text", lambda t: None)
    pressed = []
    monkeypatch.setattr(win, "hotkey", lambda k: pressed.append(k))
    ctx = make("powershell.exe", "Windows PowerShell", "")
    r = tools.call("keys", {"keys": "d"}, ctx)
    assert not r.ok and "not key by key" in r.say and not pressed
    assert tools.call("keys", {"keys": "ctrl+c"}, ctx).ok                   # a real shortcut is still fine


def test_dont_save_needs_a_yes(make):
    from core.agent_safety import check
    ctx = make("notepad.exe", "Notepad", "", controls=[{"id": 3, "name": "Don't save", "type": "Button"}])
    assert "unsaved changes" in check("click", {"control": 3}, ctx)



@pytest.mark.parametrize("how", ["number", "position", "space"])
def test_one_decision_however_a_button_is_pressed(make, monkeypatch, how):
    from core import agent_safety
    from core.agent_safety import check
    for name, exe, title, expect in [("Don't save", "notepad.exe", "Notepad", "unsaved changes"),
                                     ("OK", "explorer.exe", "Run", "run")]:
        ctx = make(exe, title, name if how == "space" else "", [typed("cmd /c del *")],
                   controls=[{"id": 2, "name": name, "type": "Button"}])
        if how == "number":
            q = check("click", {"control": 2}, ctx)
        elif how == "position":
            monkeypatch.setattr(agent_safety, "name_at", lambda x, y: name)
            ctx.look = {"region": (0, 0, 100, 100), "grid": 1000}
            q = check("click", {"x": 500, "y": 500}, ctx)
        else:
            q = check("keys", {"keys": "space"}, ctx)
        assert q and expect in q.lower(), (how, name, q)


def test_a_letter_key_is_refused_when_the_password_check_fails(make, monkeypatch):
    from core import tools
    from hands import win
    pressed = []
    monkeypatch.setattr(win, "focused_is_password", lambda: None)
    monkeypatch.setattr(win, "hotkey", lambda k: pressed.append(k))
    assert not tools.call("keys", {"keys": "a"}, make()).ok and not pressed
    assert tools.call("keys", {"keys": "ctrl+t"}, make()).ok and pressed == ["ctrl+t"]


def test_a_screenshot_click_never_lands_in_another_window(make, monkeypatch):
    from core import agent_safety, tools
    from hands import mouse, win
    clicked, focused = [], []
    monkeypatch.setattr(agent_safety, "name_at", lambda x, y: "Video title")
    monkeypatch.setattr(win, "foreground", lambda: 9)
    monkeypatch.setattr(win, "focus", lambda h: focused.append(h) or True)
    monkeypatch.setattr(mouse, "click_at", lambda x, y, **k: clicked.append((x, y)))
    ctx = make("chrome.exe", "YouTube", "")
    ctx.look = {"region": (0, 0, 1000, 1000), "grid": 1000, "hwnd": 5}
    monkeypatch.setattr(win, "window_at", lambda x, y: 9)                  # PowerShell (9) covers the spot
    r = tools.call("click", {"x": 400, "y": 300}, ctx)
    assert not r.ok and "covers that spot" in r.say and not clicked and focused == [5]
    ctx.look = {"region": (0, 0, 1000, 1000), "grid": 1000, "hwnd": 5}
    monkeypatch.setattr(win, "window_at", lambda x, y: 5)                  # the looked-at window is on top
    assert tools.call("click", {"x": 400, "y": 300}, ctx).ok and clicked == [(400, 300)]
