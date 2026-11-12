"""Skills (core/skills.py): search opens the results page and checks the address bar; save checks it saved."""
import pytest

from core import skills, tools


@pytest.fixture
def live(monkeypatch):
    """A real (not dry-run) context with Otto's own window not in front and Chrome's address bar faked."""
    from core import agent_safety
    from hands import web
    opened, shown = [], []
    monkeypatch.setattr(agent_safety, "otto_in_front", lambda c: False)
    monkeypatch.setattr(skills, "_action", lambda ctx, do, **w: opened.append((do, w)) or tools.ToolResult(True, "ok"))
    monkeypatch.setattr(web, "chrome_addresses", lambda only=None: list(shown))
    monkeypatch.setattr(skills, "SEARCH_WAIT", 0)
    return tools.ToolContext(dry_run=False), opened, shown


def test_google_search_opens_the_results_page_and_checks_it(live):
    c, opened, shown = live
    shown.append("google.com/search?q=banana+bread&sca_esv=27a2")
    r = tools.call("search", {"query": "banana bread"}, c)
    assert r.ok and opened == [("open_site", {"site": "https://www.google.com/search?q=banana+bread"})]


def test_youtube_search_has_no_typing_and_checks_the_words(live):
    c, opened, shown = live
    shown.append("https://www.youtube.com/results?search_query=lofi+music")
    r = tools.call("search", {"query": "lofi music", "where": "YouTube"}, c)
    assert r.ok and opened[0][1]["site"] == "https://www.youtube.com/results?search_query=lofi+music"


def test_the_same_word_typed_three_times_is_not_the_search(live):
    c, opened, shown = live
    shown.append("google.com/search?q=lofilofilofi&sca_esv=27a2")      # 12 Nov live test
    r = tools.call("search", {"query": "lofi", "where": "google"}, c)
    assert not r.ok and "doesn't show it" in r.say


def test_another_site_in_the_address_bar_is_not_the_search(live):
    c, opened, shown = live
    shown.append("https://www.google.com/search?q=lofi")
    assert not tools.call("search", {"query": "lofi", "where": "youtube"}, c).ok


def test_spotify_search_uses_the_app(live):
    c, opened, shown = live
    assert tools.call("search", {"query": "lofi beats", "where": "spotify"}, c).ok
    assert opened == [("search_in_app", {"app": "spotify", "query": "lofi beats"})]


def test_google_is_still_understood_as_search(live):
    c, opened, shown = live
    shown.append("google.com/search?q=banana+bread")
    assert tools.call("google", {"query": "banana bread"}, c).ok


def test_search_in_a_dry_run_does_nothing():
    r = tools.call("search", {"query": "lofi", "where": "youtube"}, tools.ToolContext(dry_run=True))
    assert r.ok and "would search youtube" in r.say


# ---- save ----
@pytest.fixture
def notepad(monkeypatch):
    """Windows 11 Notepad: the title has no mark; the tab is named "notes.txt. Modified." until saved."""
    from core import agent_safety
    from hands import win
    state = {"tab": "notes.txt. Modified.", "after": "notes.txt. Unmodified.", "pressed": []}
    monkeypatch.setattr(agent_safety, "otto_in_front", lambda c: False)
    monkeypatch.setattr(agent_safety, "front", lambda c: {"hwnd": 7, "exe": "notepad.exe", "title": "notes.txt - Notepad",
                                                          "focused": "Text editor"})
    monkeypatch.setattr(skills, "_tab_names", lambda hwnd: [state["tab"], "Add New Tab"])
    monkeypatch.setattr(win, "focused_is_password", lambda: False)
    monkeypatch.setattr(win, "hotkey", lambda keys: state["pressed"].append(keys) or state.update(tab=state["after"]))
    monkeypatch.setattr(skills, "SAVE_WAIT", 0)
    return tools.ToolContext(dry_run=False), state


def test_save_is_confirmed_by_notepads_tab(notepad):
    c, state = notepad
    r = tools.call("save", {}, c)
    assert r.ok and r.observed["saved"] is True and state["pressed"] == ["ctrl+s"]


def test_save_not_confirmed_while_the_tab_still_says_modified(notepad):
    c, state = notepad
    state["after"] = "notes.txt. Modified."
    r = tools.call("save", {}, c)
    assert not r.ok and r.observed["saved"] is False and "unsaved changes" in r.say


def test_ctrl_s_through_keys_is_the_save_skill(notepad):
    c, state = notepad
    r = tools.call("keys", {"keys": "Ctrl + S"}, c)
    assert r.observed.get("saved") is True


def test_another_tab_does_not_count(notepad):
    c, state = notepad
    state["tab"] = state["after"] = "other.txt. Unmodified."
    r = tools.call("save", {}, c)
    assert r.ok and r.observed["saved"] is False and "couldn't confirm" in r.say


def test_a_failed_save_overrides_qwens_saved(notepad):
    from core import agent
    from tests.test_agent import Scripted, call
    c, state = notepad
    state["after"] = "notes.txt. Modified."
    r = agent.run("type hi and save it", [], Scripted(call("save"), call("done", say="Saved it!")), c)
    assert not r.ok and "unsaved changes" in r.say


def test_skills_keep_the_menu_small():
    assert "google" not in tools.TOOLS and {"search", "save"} <= set(tools.TOOLS)
    assert len(tools.TOOLS) <= 20
