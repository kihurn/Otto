"""Fixes from the second live run of goal mode: knowing when it is finished, never pressing the same thing
twice, answering questions, a few safe keys, no accidental typing, Spotify names, and closing apps."""
from types import SimpleNamespace as N
import pytest
from core import goal_mode, interpreter, safety
from core.tasks import OutcomeStatus
from hands import media, registry, spotify_desktop, ui_probe, win
from test_goal_mode import app, control, qwen  # noqa: F401  (the pretend app and scripted Qwen)
import core.methods as methods


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    registry.load_all()
    monkeypatch.setattr(methods, 'METHODS_FILE', tmp_path / 'methods.json')


# --- 1. knowing when it is finished ------------------------------------------------------------------

def test_playing_the_asked_playlist_ends_the_task(app, monkeypatch):
    monkeypatch.setattr(media, 'sessions', lambda: [{'app': 'Spotify.exe', 'status': media.PLAYING}])
    app.controls = [control('Button', 'Play My playlist #9'), control('Button', 'Play PRETTY PLEASE by Dutch Melrose')]
    app.screens = {'Play My playlist #9': [control('Button', 'Pause My playlist #9'),
                                          control('Button', 'Play PRETTY PLEASE by Dutch Melrose')]}
    # Qwen would happily keep clicking; the code check stops it after the first press.
    result = goal_mode.pursue('spotify', 'play my playlist number nine',
                              propose=qwen(app, ('click', 'Play My playlist #9'),
                                           ('click', 'Play PRETTY PLEASE by Dutch Melrose')))
    assert result.status == OutcomeStatus.VERIFIED and app.pressed == ['Play My playlist #9']
    assert result.data['judged_by'] == 'code' and 'My playlist #9' in result.say


@pytest.mark.parametrize('button,goal,same', [
    ('Play My playlist #9', 'play my playlist number nine', True),
    ('Play for the rat', 'can you play for the rat', True),
    ('Play PRETTY PLEASE by Dutch Melrose, benny mayne', 'play my playlist number nine', False),
    ('Play', 'play something', False),
])
def test_is_this_the_thing_that_was_asked_for(button, goal, same):
    assert goal_mode.same_thing(button, goal) is same


def test_qwen_is_asked_whether_it_is_finished_after_each_step(app):
    app.controls = [control('MenuItem', 'View')]
    app.screens = {'View': [control('MenuItem', 'View'), control('CheckBox', 'Status bar', checked=True)]}
    asked = []

    def judge(goal, name, controls, history, deadline):
        asked.append(list(history))
        return True
    result = goal_mode.pursue('notepad', 'show the view menu', propose=qwen(app, ('click', 'View'), ('click', 'Status bar')),
                              judge=judge)
    assert result.status == OutcomeStatus.VERIFIED and app.pressed == ['View'] and len(asked) == 1
    assert result.data['judged_by'] == 'qwen'


def test_the_same_control_is_never_pressed_twice(app):
    app.controls = [control('Button', 'Playlists')]
    app.screens = {'Playlists': [control('Button', 'Playlists'), control('Button', 'By you')]}
    result = goal_mode.pursue('spotify', 'tidy my library', propose=qwen(app, *[('click', 'Playlists')] * 6))
    assert app.pressed == ['Playlists'] and result.status == OutcomeStatus.NEEDS_INPUT


# --- 2. answering questions --------------------------------------------------------------------------

def test_a_question_gets_an_answer_not_clicks(app):
    app.controls = [control('Button', 'Rock Kihurn'), control('Button', 'EDM Kihurn')]

    def propose(prompt, image, deadline):
        assert '"answer"' in prompt
        return {'action': 'answer', 'id': 0, 'why': 'counted', 'answer': 'I can see 2 playlists.'}
    result = goal_mode.pursue('spotify', 'How many playlists do I have?', propose=propose)
    assert result.status == OutcomeStatus.VERIFIED and result.say == 'I can see 2 playlists.' and app.pressed == []


def test_answer_is_only_offered_for_questions():
    assert goal_mode.is_question('How many playlists do I have?') and goal_mode.is_question('count my playlists')
    assert not goal_mode.is_question('press save')
    with pytest.raises(ValueError):
        goal_mode.validate({'action': 'answer', 'id': 0, 'answer': 'hi'}, [], can_type=False, can_answer=False)


# --- 5. a few safe keys ------------------------------------------------------------------------------

def test_delete_key_only_when_the_user_asked_to_delete():
    assert 'delete' in goal_mode.allowed_keys('remove all the words') and 'delete' not in goal_mode.allowed_keys('make it bold')
    assert 'enter' not in goal_mode.KEYS                      # Enter can mean Send
    with pytest.raises(ValueError):
        goal_mode.validate({'action': 'key', 'id': 0, 'key': 'delete'}, [], False, False, goal_mode.allowed_keys('make it bold'))
    with pytest.raises(ValueError):
        goal_mode.validate({'action': 'key', 'id': 0, 'key': 'alt+f4'}, [], False, False, goal_mode.allowed_keys('remove it'))


def test_select_all_then_delete_clears_the_document(app, monkeypatch):
    app.controls = [control('Document', 'Page 1', focused=True)]
    app.text = 'Hello there'
    sent = []

    def hotkey(keys):
        sent.append(keys)
        if keys == 'delete':
            app.text = ''
    monkeypatch.setattr(win, 'hotkey', hotkey)
    picks = iter([{'action': 'key', 'id': 0, 'why': 'select', 'key': 'select_all'},
                  {'action': 'key', 'id': 0, 'why': 'clear', 'key': 'delete'}])
    result = goal_mode.pursue('word', 'remove all the words', propose=lambda *a: next(picks))
    assert sent == ['ctrl+a', 'delete'] and result.status == OutcomeStatus.VERIFIED and result.say == 'Cleared it.'


def test_keys_are_not_sent_into_a_password_box_or_another_window(app, monkeypatch):
    app.controls = [control('Edit', 'Notes', focused=True)]
    monkeypatch.setattr(win, 'focused_is_password', lambda: True)
    monkeypatch.setattr(win, 'hotkey', lambda keys: pytest.fail('key sent'))
    result = goal_mode.pursue('word', 'remove all the words',
                              propose=lambda *a: {'action': 'key', 'id': 0, 'why': '', 'key': 'delete'})
    assert result.status == OutcomeStatus.UNCERTAIN


# --- 3. no accidental typing -------------------------------------------------------------------------

class Apps:
    def match_exact(self, name):
        return {'name': 'Word'} if name == 'word' else None

    def match(self, name):
        return (None, 0, [])


@pytest.mark.parametrize('said,typed,allowed', [
    ('you should check out', 'you should check out', False),          # a stray remark, no typing word
    ('can you write I am Otto', 'I am Otto', True),
    ('type hello there in word', 'hello there', True),
    ('write this down', 'write this down', False),                    # the "text" is the whole sentence
])
def test_qwen_can_only_type_what_was_asked_to_be_typed(said, typed, allowed):
    reply = {'choice': 'apps.type_in_app', 'params': {'app': 'word', 'text': typed}, 'sure': True}
    intent, _, _ = interpreter.to_intent(reply, said, Apps(), last_app='Word')
    assert (intent is not None) is allowed


# --- 4. Spotify names --------------------------------------------------------------------------------

@pytest.mark.parametrize('heard', ['number nine', 'my playlist number nine', '#9', 'number 9'])
def test_number_nine_is_hash_nine(heard):
    assert 'my playlist 9' in spotify_desktop.playlist_names(heard)


def test_a_playlist_in_the_library_wins_over_a_song_search(monkeypatch):
    import time
    from core.tasks import Step, Task
    monkeypatch.setattr(win, 'find_window', lambda name: {'hwnd': 1})
    monkeypatch.setattr(win, 'window_info', lambda hwnd: {'rect': (0, 0, 1000, 800)})
    monkeypatch.setattr(ui_probe, 'list_controls', lambda hwnd, limit=150: [
        {'type': 'Button', 'name': 'Play for the rat', 'rect': (60, 100, 100, 140), 'enabled': True}])
    assert spotify_desktop.in_library('for the rat') and not spotify_desktop.in_library('over the moon')
    went = []
    monkeypatch.setattr(spotify_desktop, 'play_playlist', lambda step, task, end, progress: went.append(step.args['query']) or 'playlist')
    step = Step('s', 'play_music', {'query': 'for the rat', 'kind': 'auto', 'artist': ''})
    assert spotify_desktop.play(step, Task('play', [step]), time.monotonic() + 45, lambda text: None) == 'playlist'
    assert went == ['for the rat']


# --- 6. closing an app -------------------------------------------------------------------------------

@pytest.mark.parametrize('still_open,expected_ok,phrase', [(False, True, 'Closed Word.'), (True, False, 'still there')])
def test_closing_is_confirmed_by_the_window_going_away(monkeypatch, still_open, expected_ok, phrase):
    from core import executor
    from hands.registry import Result
    monkeypatch.setattr(win, 'IS_WINDOWS', True)
    monkeypatch.setattr(win, 'find_window', lambda name: {'hwnd': 5} if still_open else None)
    monkeypatch.setattr(executor.time, 'sleep', lambda n: None)
    monkeypatch.setattr(registry.ACTIONS['close_app'], 'fn', lambda app: Result(True, 'Closing Word.'))
    result = safety.run_plan([{'do': 'close_app', 'with': {'app': 'word'}}], confirmed=True)
    assert result.ok is expected_ok and phrase in result.say
