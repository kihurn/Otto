"""Regression tests for problems found in the 1.2 live Windows checks (11 Nov 2026)."""
import sys
from types import SimpleNamespace as N
import pytest
from core import compiler, safety
from core.details import _web
from core.search_goals import new_tab
from hands import apps, registry, web, win


@pytest.fixture(autouse=True)
def actions():
    registry.load_all()


# --- 1. Spotify reports its search text a moment after it is set -------------------------------------

class SlowValue:
    """A search box that keeps reporting the old text for a few reads, like the real Spotify."""
    CurrentIsReadOnly = False

    def __init__(self, late_reads):
        self.shown, self.pending, self.late_reads = 'old search', None, late_reads

    def SetValue(self, query):
        self.pending = query

    @property
    def CurrentValue(self):
        if self.pending is not None:
            if self.late_reads <= 0:
                self.shown, self.pending = self.pending, None
            self.late_reads -= 1
        return self.shown


def spotify_with(monkeypatch, value):
    from hands import spotify_search as search
    control = N(window_text=lambda: 'What do you want to play?', is_visible=lambda: True,
                is_enabled=lambda: True, element_info=N(element=N(CurrentIsPassword=False)),
                iface_value=value, set_focus=lambda: None, has_keyboard_focus=lambda: False)
    dialog = N(descendants=lambda **kw: [control])
    monkeypatch.setitem(sys.modules, 'pywinauto',
                        N(Application=lambda **kw: N(connect=lambda **kw: N(window=lambda **kw: dialog))))
    monkeypatch.setattr(win, 'foreground', lambda: 7)
    monkeypatch.setattr(win, 'hotkey', lambda *a: pytest.fail('unverified global keystroke'))
    monkeypatch.setattr(search.time, 'sleep', lambda n: None)
    return search


def test_spotify_search_waits_for_late_readback(monkeypatch):
    search = spotify_with(monkeypatch, SlowValue(late_reads=5))
    assert search.search(7, 'The Hills The Weeknd').ok


def test_spotify_search_still_stops_if_text_never_matches(monkeypatch):
    search = spotify_with(monkeypatch, SlowValue(late_reads=10_000))
    result = search.search(7, 'The Hills The Weeknd')
    assert not result.ok and result.data['error_code'] == 'value_mismatch'


# --- 2. "open a new tab on chrome and search hello world" --------------------------------------------

@pytest.mark.parametrize('text,expected', [
    ('open a new tab on chrome', True),
    ('can you open a new tab in Google Chrome?', True),
    ('open new tab', True),
    ('open my new tab notes file', False),
    ('open chrome', False),
])
def test_new_tab_phrases(text, expected):
    assert new_tab(text) is expected


def test_new_tab_then_search_is_one_web_search():
    plan = compiler.compile_request('can you open a new tab on chrome and search hello world', apps.INDEX, None)
    assert not plan.error
    assert [(s['do'], s['with']) for s in plan.steps] == [('web_search', {'query': 'hello world'})]


def test_new_tab_alone_opens_a_tab_not_a_file_search():
    intent = _web('open a new tab on chrome')
    assert (intent.action, intent.params) == ('open_site', {'site': 'new tab'})
    plan = compiler.compile_request('open a new tab on chrome then set volume to 30', apps.INDEX, None)
    assert [s['do'] for s in plan.steps] == ['open_site', 'set_volume']


# --- 3. Opened websites are checked against Chrome's address bar -------------------------------------

@pytest.mark.parametrize('shown,wanted,same', [
    ('mail.google.com/mail/u/0/#inbox', 'https://mail.google.com', True),
    ('youtube.com', 'https://www.youtube.com', True),
    ('google.com/search?q=hello%20world', 'https://www.google.com/search?q=hello%20world', True),
    ('google.com/search?q=something+else', 'https://www.google.com/search?q=hello%20world', False),
    ('evil.example/mail.google.com', 'https://mail.google.com', False),
    ('', 'https://mail.google.com', False),
    ('google.com', web.NEW_TAB, True),
])
def test_same_page(shown, wanted, same):
    assert web.same_page(shown, wanted) is same


@pytest.mark.parametrize('seen', [True, False])
def test_open_site_is_verified_only_when_chrome_shows_it(monkeypatch, seen):
    monkeypatch.setattr(win, 'IS_WINDOWS', True)
    monkeypatch.setattr(web, 'open_in_browser', lambda url: None)
    monkeypatch.setattr(web, 'site_url', lambda site: 'https://mail.google.com')
    monkeypatch.setattr(web, 'shown_in_chrome', lambda url: seen)
    result = safety.run_plan([{'do': 'open_site', 'with': {'site': 'gmail'}}])
    assert result.ok is seen
    assert result.say == ('Opened gmail.' if seen else "Opening gmail. I couldn't confirm it loaded.")


# --- 4. Second live run: duplicate Spotify results, "note pad", and typing into other apps -----------

def test_spotify_duplicate_results_pick_the_top_one(monkeypatch):
    import time
    from core.tasks import OutcomeStatus, Step, Task
    from hands import media, spotify_desktop
    from hands.registry import Result
    monkeypatch.setattr(apps, 'open_app', lambda *a: Result(True, 'opened'))
    monkeypatch.setattr(apps, 'search_in_app', lambda *a: Result(True, 'searched'))
    monkeypatch.setattr(win, 'find_window', lambda *a: {'hwnd': 1})
    monkeypatch.setattr(win, 'foreground', lambda: 1)
    monkeypatch.setitem(sys.modules, 'pywinauto',
                        N(Application=lambda **kw: N(connect=lambda **kw: N(window=lambda **kw: object()))))
    pressed = []
    def button(name, top):
        return N(rectangle=lambda: N(top=top, left=500), invoke=lambda: pressed.append(name))
    # The same song as a row in Songs (lower on the page) and as the Top result card (higher).
    monkeypatch.setattr(spotify_desktop, 'play_candidates',
                        lambda *a: [button('songs row', 680), button('top result', 260), button('songs row 2', 744)])
    monkeypatch.setattr(media, 'sessions', lambda: [{'app': 'Spotify', 'status': media.PLAYING,
                                                     'title': 'The Hills', 'artist': 'The Weeknd'}])
    step = Step('s', 'play_music', {'query': 'The Hills', 'artist': 'The Weeknd'})
    result = spotify_desktop.play(step, Task('play', [step]), time.monotonic() + 45, lambda text: None)
    assert result.status == OutcomeStatus.VERIFIED and pressed == ['top result']


@pytest.mark.parametrize('text', ['can you type hello world in note pad?', 'type hello world in notepad',
                                  'write hello world into Notepad.'])
def test_note_text_drops_the_notepad_part(text):
    from core.details import _notes
    assert _notes(text).params == {'text': 'hello world'}


def test_compound_volume_pronoun_keeps_the_amount():
    plan = compiler.compile_request('set volume to 70, then lower it by thirty two', apps.INDEX, None)
    assert [(s['do'], s['with']) for s in plan.steps] == [('set_volume', {'level': 70}), ('change_volume', {'step': -32})]
    plan = compiler.compile_request('set volume to 70, then increase it to 80', apps.INDEX, None)
    assert [(s['do'], s['with']) for s in plan.steps] == [('set_volume', {'level': 70}), ('set_volume', {'level': 80})]
