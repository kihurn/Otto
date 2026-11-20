import pytest
from core.guards import filler_only

from hands.spotify_desktop import matches, normalized
from tests.test_pipeline import otto  # noqa: F401  (the fake-Laya, fake-brain Otto)


@pytest.mark.parametrize('text', ['um', 'uhh', 'uhms', 'umm, uh', 'erm', 'Oh', 'oh.', 'ahh', 'huh?', 'mm', 'mhm', 'oh, hmm'])
def test_fillers(text):
    assert filler_only(text)


@pytest.mark.parametrize('text', ['play um', 'search for uhm', 'hmm play music', 'oh no', 'oh yeah', 'ah pause'])
def test_real_content_not_discarded(text):
    assert not filler_only(text)




def test_spotify_desktop_matching():
    assert matches('Play Over the Moon by The Marías', 'Over the Moon', 'The Marias')
    assert not matches('Play Over the Moon by someone else', 'Over the Moon', 'The Marias')
    assert normalized('The Weekend') == normalized('The Weeknd')


def test_desktop_route_does_not_call_api(monkeypatch):
    from core import executor, config
    from core.tasks import Step, Task, Outcome, OutcomeStatus
    from hands import spotify_desktop
    from connectors import spotify
    monkeypatch.setattr(config, 'load_settings', lambda: {'spotify': {'playback_backend': 'desktop'}})
    monkeypatch.setattr(spotify, '_call', lambda *a, **kw: pytest.fail('Desktop must not call API'))
    monkeypatch.setattr(spotify_desktop, 'play', lambda *a: Outcome(OutcomeStatus.UNCERTAIN, 'UI unavailable'))
    assert executor.music_step(Step('s', 'play_music', {'query': 'x'}), Task('x', []), 100, lambda m: None).say == 'UI unavailable'


@pytest.mark.parametrize('count', [1, 2])
def test_desktop_invokes_one_matching_control(monkeypatch, count):
    # Two matches are the same song listed twice (Top result and Songs); exactly one is pressed.
    import sys
    from types import SimpleNamespace
    from hands import apps, media, win, spotify_desktop as ui
    from hands.registry import Result
    from core.tasks import Task, Step
    clicked = []
    ctrl = SimpleNamespace(window_text=lambda: 'Play Over the Moon by The Marias',
                           is_visible=lambda: True, is_enabled=lambda: True,
                           invoke=lambda: clicked.append(True),
                           rectangle=lambda: SimpleNamespace(top=100, left=100))
    dialog = SimpleNamespace(descendants=lambda **kw: [ctrl] * count)
    app = SimpleNamespace(connect=lambda **kw: SimpleNamespace(window=lambda **kw: dialog))
    monkeypatch.setitem(sys.modules, 'pywinauto', SimpleNamespace(Application=lambda **kw: app))
    monkeypatch.setattr(apps, 'open_app', lambda *a: Result(True, 'opened'))
    monkeypatch.setattr(apps, 'search_in_app', lambda *a: Result(True, 'searched'))
    monkeypatch.setattr(win, 'find_window', lambda *a: {'hwnd': 1})
    monkeypatch.setattr(win, 'foreground', lambda: 1)
    monkeypatch.setattr(media, 'sessions', lambda: [{'app': 'Spotify.exe', 'title': 'Over the Moon',
                                                   'artist': 'The Marías', 'status': media.PLAYING}])
    task = Task('play', [])
    outcome = ui.play(Step('s', 'play_music', {'query': 'Over the Moon', 'artist': 'The Marias'}),
                      task, float('inf'), lambda m: None)
    assert outcome.ok and len(clicked) == 1


def test_a_quiet_oh_gets_no_question(otto):
    # 20 Nov voice run: "Oh" (heard at -1.12) got "Sorry, did you say "Oh"?". A filler gets no reply at all.
    assert otto.handle("Oh", heard_conf=-1.12).text == ""
    assert otto.pending is None or otto.pending.kind != "heard"
