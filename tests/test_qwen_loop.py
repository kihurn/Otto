"""Qwen in the loop: the interpreter (what does this request mean, given the conversation?), the supervisor
(that didn't work, what now?), misheard names, and the fixed voice phrases. Qwen is faked throughout."""
from types import SimpleNamespace as N
import pytest
from core import interpreter
from core.details import Intent
from core.tasks import OutcomeStatus
from hands import spotify_desktop, ui_probe
from test_pipeline import otto  # noqa: F401  (the shared pretend-Otto: dry run, fake Laya, fake brain)


class Apps:
    """A tiny pretend list of installed apps."""
    names = {'notepad': 'Notepad', 'word': 'Word', 'spotify': 'Spotify'}

    def match_exact(self, name):
        return {'name': self.names[name]} if name in self.names else None

    def match(self, name):
        return (None, 0, [])


def brain(reply):
    return N(ask=lambda *a, **k: N(data=reply, model='fake-qwen'))


HISTORY = [{'you': 'can you open notepad', 'otto': 'Opened Notepad.'}]


# --- the interpreter ---------------------------------------------------------------------------------

def test_save_this_file_after_opening_notepad_means_notepad():
    reply = {'choice': 'apps.app_goal', 'params': {'goal': 'save this file'}, 'sure': True}
    intent, question, sure = interpreter.interpret('can you save this file', HISTORY, 'Notepad', '', Apps(), brain(reply))
    assert (intent.area, intent.action, intent.params) == ('apps', 'app_goal', {'app': 'Notepad', 'goal': 'save this file'})
    assert sure and not question


def test_prompt_carries_the_conversation_and_the_last_app():
    prompt = interpreter.build_prompt('can you save this file', HISTORY, 'Notepad', 'Untitled - Notepad (Notepad.exe)')
    assert 'User: can you open notepad' in prompt and 'App Otto last worked in: Notepad' in prompt
    assert 'apps.app_goal' in prompt and len(prompt) < 6000          # well inside the 8192-token limit


@pytest.mark.parametrize('reply', [
    {'choice': 'shell.run', 'params': {'command': 'del *'}, 'sure': True},                 # not on the menu
    {'choice': 'apps.type_in_app', 'params': {'app': 'word', 'text': 'I love you'}, 'sure': True},  # invented words
    {'choice': 'notes.new_note', 'params': {'text': 'buy milk'}, 'sure': True},            # invented words
    {'choice': 'apps.click_button', 'params': {'app': 'word'}, 'sure': True},              # no button named
    {'choice': 'media.set_volume', 'params': {'level': 'loud'}, 'sure': True},
    'open notepad',
])
def test_answers_off_the_menu_or_made_up_are_dropped(reply):
    intent, _, _ = interpreter.to_intent(reply, 'please do the thing in word', Apps())
    assert intent is None


def test_unknown_app_becomes_a_question_and_extra_params_are_removed():
    intent, question, _ = interpreter.to_intent({'choice': 'apps.open', 'params': {'app': 'photoshop'}}, 'open it', Apps())
    assert intent is None and 'Which app' in question
    intent, _, _ = interpreter.to_intent({'choice': 'media.next', 'params': {'command': 'rm'}, 'sure': True}, 'change the song', Apps())
    assert (intent.action, intent.params) == ('next', {})


def test_clarify_passes_the_question_through():
    intent, question, sure = interpreter.to_intent({'choice': 'ask.clarify', 'question': 'Save it in Notepad?'}, 'save', Apps())
    assert intent is None and question == 'Save it in Notepad?' and not sure


@pytest.mark.parametrize('intent,text,odd', [
    (Intent('notes', 'new_note', {'text': 'Can you open Notepad?'}, source='brain'), 'Can you open Notepad?', True),
    (Intent('notes', 'new_note', {'text': 'hello there'}), 'can you write hello there in notepad', False),
    (Intent('files', 'find', {'query': 'save'}), 'could you save my file', True),
    (Intent('files', 'find', {'query': 'resume'}), 'find my resume', False),
    (Intent('media', 'play_pause', {}, source='brain'), 'could you change the song', True),
    (Intent('media', 'set_volume', {'level': 30}), 'set volume to 30', False),
    (None, 'will you close the word', True),
])
def test_which_fast_answers_get_a_second_look(intent, text, odd):
    assert interpreter.suspicious(intent, text) is odd


# --- inside the pipeline (dry run, fake Laya) --------------------------------------------------------

def test_pipeline_uses_qwen_when_the_rules_have_nothing(otto, monkeypatch):
    seen = {}

    def interpret(text, history, last_app, window, apps_index, brain_):
        seen.update(text=text, turns=len(history))
        return Intent('media', 'next', {}, source='brain'), '', True
    monkeypatch.setattr(interpreter, 'interpret', interpret)
    monkeypatch.setattr(otto.router, 'predict', lambda t: {'area': 'media', 'prob': 0.99, 'ms': 1, 'top': []})
    monkeypatch.setattr(otto.router, 'zone', lambda p: 'high')
    reply = otto.handle('could you change the song')
    assert seen['text'] == 'could you change the song' and 'skip to the next track' in reply.text


def test_pipeline_asks_before_acting_when_qwen_is_not_sure(otto, monkeypatch):
    monkeypatch.setattr(interpreter, 'interpret', lambda *a: (Intent('media', 'pause', {}, source='brain'), '', False))
    monkeypatch.setattr(otto.router, 'predict', lambda t: {'area': 'media', 'prob': 0.3, 'ms': 1, 'top': []})
    monkeypatch.setattr(otto.router, 'zone', lambda p: 'low')
    reply = otto.handle('make it stop please now')
    assert reply.text.endswith('?') and otto.pending.kind == 'confirm_area'


def test_app_named_first_is_understood(otto, monkeypatch):
    monkeypatch.setattr(otto.apps, 'match_exact', lambda name: {'name': 'Notepad'} if name == 'notepad' else None, raising=False)
    reply = otto.handle('In notepad, can you click view then click status?')
    assert reply.text.count('in notepad') == 2 and 'search your files' not in reply.text


def test_quiet_save_that_is_accepted_but_a_quiet_yes_is_not(otto):
    otto.handle('close discord')                       # leaves a "should I close Discord?" question open
    assert otto.pending is not None
    assert 'repeat your answer' in otto.handle('yes', heard_conf=-1.2).text
    assert 'repeat your answer' not in otto.handle('save that', heard_conf=-1.2).text


# --- the supervisor ----------------------------------------------------------------------------------

def test_review_only_offers_what_makes_sense():
    assert interpreter.review('save it', 'click save', 'no button', 'Notepad',
                              brain({'next': 'work_it_out', 'goal': 'save the file'})) == {'next': 'work_it_out', 'goal': 'save the file'}
    # No app involved: there is no window to work in, so that choice is ignored.
    assert interpreter.review('x', 'y', 'z', '', brain({'next': 'work_it_out', 'goal': 'g'})) == {'next': 'leave'}
    assert interpreter.review('x', 'y', 'z', '', brain({'next': 'ask', 'question': 'Which file?'}))['question'] == 'Which file?'
    assert interpreter.review('x', 'y', 'z', 'Word', brain({'next': 'format the disk'})) == {'next': 'leave'}


def test_supervisor_never_runs_in_dry_run_or_twice(otto, monkeypatch):
    from core import planner
    monkeypatch.setattr(interpreter, 'review', lambda *a: pytest.fail('supervisor ran when it must not'))
    failed = N(ok=False, say='nope', data={'outcome_status': 'failed'})
    plan = planner.Plan([{'do': 'click_button', 'with': {'app': 'notepad', 'button': 'save'}}], 'builtin')
    assert otto._supervise('click save in notepad', plan, failed) is None          # otto fixture is a dry run
    otto.dry_run, otto._supervising = False, True
    assert otto._supervise('click save in notepad', plan, failed) is None
    otto._supervising = False
    stuck = N(ok=False, say="I'm not sure how", data={'outcome_status': 'needs_input', 'goal_mode': True})
    assert otto._supervise('click save in notepad', plan, stuck) is None            # goal mode already tried


# --- misheard names ----------------------------------------------------------------------------------

def library(*names):
    return [{'name': f'Play {name}', 'rect': (60, 100 + 60 * i, 100, 140 + 60 * i)} for i, name in enumerate(names)]


@pytest.mark.parametrize('heard', ['for the red', 'for the rack', 'for the wrap'])
def test_misheard_playlist_finds_the_real_one(heard):
    guess, score = spotify_desktop.closest_playlist(library('for the rat', 'Rock', 'EDM', 'My playlist #9'),
                                                    heard, (0, 0, 1000, 800))
    assert guess == 'for the rat' and score >= 80


def test_no_wild_guesses_at_playlists():
    buttons = library('Rock', 'EDM', 'My playlist #9')
    assert spotify_desktop.closest_playlist(buttons, 'for the rat', (0, 0, 1000, 800)) == (None, 0)
    # Song rows on the right-hand side of the window are not playlists.
    far_right = [{'name': 'Play for the rat', 'rect': (700, 100, 740, 140)}]
    assert spotify_desktop.closest_playlist(far_right, 'for the red', (0, 0, 1000, 800)) == (None, 0)


def test_nearly_right_button_name_is_matched_only_when_clear():
    def named(name):
        return {'name': name, 'type': 'Button'}
    assert ui_probe.closest([named('Status bar'), named('Zoom')], 'statis bar')[0]['name'] == 'Status bar'
    assert ui_probe.closest([named('Save'), named('Save As')], 'export') == (None, False)
    assert ui_probe.closest([named('Row 1'), named('Row 2')], 'Row 3') == (None, False)     # two equally near


def test_indicator_is_silent_outside_live_tasks():
    from hands import indicator
    indicator.show(123)
    indicator.point((0, 0, 10, 10))
    indicator.hide()
    assert indicator._commands is None                 # no overlay window was ever created
