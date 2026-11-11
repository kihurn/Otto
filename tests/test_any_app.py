"""Any-app control, slice 1: reading a window's controls, the private-field guard, and typing into an app.
Everything Windows-specific is faked, so these run on any computer."""
from types import SimpleNamespace as N
import pytest
from core import compiler, details
from core.sensitive import sensitive
from core.tasks import OutcomeStatus
from hands import app_control, apps, registry, ui_probe, win


@pytest.fixture(autouse=True)
def actions():
    registry.load_all()


def control(kind='Edit', name='', **extra):
    base = {'id': 1, 'name': name, 'type': kind, 'automation_id': '', 'rect': (0, 0, 100, 20),
            'password': False, 'enabled': True, 'focused': False, 'read_only': False, 'element': N(SetFocus=lambda: None)}
    return dict(base, **extra)


# --- the private-field guard -------------------------------------------------------------------------

@pytest.mark.parametrize('made,expected', [
    (control(name='Password'), True),
    (control(name='', password=True), True),
    (control(name='Card number'), True),
    (control(name='', automation_id='cardNumber'), True),
    (control(name='Verification code'), True),
    (control(name='Search'), False),
    (control('Document', name='Text editor'), False),
    (control('Button', name='Show password'), False),     # a button is not a field to type in
    (control(name='Pinned notes'), False),                 # "pin" must be a whole word
])
def test_sensitive_fields(made, expected):
    assert sensitive(made) is expected


# --- finding controls --------------------------------------------------------------------------------

def test_find_control_prefers_exact_name_and_reports_ties():
    save, save_as = control('Button', 'Save'), control('Button', 'Save As')
    assert ui_probe.find_control([save_as, save], 'save') == (save, True)
    assert ui_probe.find_control([save_as, save], 'sav')[1] is False        # two equally good matches
    assert ui_probe.find_control([save], 'Print') == (None, False)


def test_control_at_picks_the_smallest_control_under_the_point():
    panel = control('ListItem', 'Row', rect=(0, 0, 400, 100))
    button = control('Button', 'Play', rect=(10, 10, 50, 50))
    assert ui_probe.control_at([panel, button], 20, 20) is button
    assert ui_probe.control_at([panel, button], 300, 20) is panel
    assert ui_probe.control_at([panel, button], 900, 900) is None


@pytest.mark.parametrize('controls,expected', [
    ([control('Document', 'Text editor')], ('Text editor', '')),                       # a lone editor
    ([control('Edit', 'Address and search bar')], (None, 'unclear')),                  # a lone small box: ask
    ([control('Edit', 'Find'), control('Document', 'Page', focused=True)], ('Page', '')),
    ([control('Document', 'Web page', read_only=True)], (None, 'none')),               # a web page is not an editor
    ([control('Edit', 'Password', focused=True, password=True)], (None, 'protected')),
    ([control('Button', 'OK')], (None, 'none')),
])
def test_text_target(controls, expected):
    target, reason = ui_probe.text_target(controls)
    assert (target and target['name'], reason) == expected


# --- typing into an app ------------------------------------------------------------------------------

@pytest.fixture
def fake_app(monkeypatch):
    """A pretend Word window with one focused document whose text we can watch."""
    state = N(text='Dear team, ', typed=[], controls=[control('Document', 'Page 1', focused=True)], foreground=7)
    monkeypatch.setattr(app_control, 'front_window', lambda app: ({'hwnd': 7}, 'Word', ''))
    monkeypatch.setattr(ui_probe, 'list_controls', lambda hwnd: state.controls)
    monkeypatch.setattr(ui_probe, 'read_text', lambda target: state.text)
    monkeypatch.setattr(win, 'foreground', lambda: state.foreground)
    monkeypatch.setattr(win, 'focused_is_password', lambda: False)
    monkeypatch.setattr(app_control.time, 'sleep', lambda n: None)

    def type_text(text):
        state.typed.append(text)
        state.text += text
    monkeypatch.setattr(win, 'type_text', type_text)
    return state


def test_typing_is_verified_when_the_text_appears(fake_app):
    result = app_control.type_in_app('word', 'whats up dawg')
    assert result.status == OutcomeStatus.VERIFIED and fake_app.typed == ['whats up dawg']


def test_typing_is_not_claimed_when_nothing_appears(fake_app, monkeypatch):
    monkeypatch.setattr(win, 'type_text', fake_app.typed.append)          # keys sent, document unchanged
    result = app_control.type_in_app('word', 'whats up dawg')
    assert result.status == OutcomeStatus.UNCERTAIN and "couldn't see" in result.say


@pytest.mark.parametrize('controls,phrase', [
    ([control('Button', 'Blank document')], 'anywhere to type'),                        # Word's start screen
    ([control('Edit', 'Password', focused=True, password=True)], 'never type'),
    ([control('Edit', 'Card number', focused=True)], 'never type'),
])
def test_no_keys_are_sent_without_a_safe_target(fake_app, controls, phrase):
    fake_app.controls = controls
    result = app_control.type_in_app('word', 'hello')
    assert result.status == OutcomeStatus.NEEDS_INPUT and phrase in result.say and fake_app.typed == []


def test_no_keys_are_sent_if_the_window_loses_focus(fake_app):
    fake_app.foreground = 99
    assert app_control.type_in_app('word', 'hello').status == OutcomeStatus.UNCERTAIN and fake_app.typed == []


# --- the words that lead there -----------------------------------------------------------------------

@pytest.fixture
def word_installed(monkeypatch):
    monkeypatch.setattr(apps.INDEX, 'match_exact', lambda name: name in {'word', 'notepad'}, raising=False)


def test_open_app_then_write_types_into_that_app(word_installed):
    plan = compiler.compile_request('open word and write "Whats up dawg"', apps.INDEX, None)
    assert [(s['do'], s['with']) for s in plan.steps] == [
        ('open_app', {'app': 'Word'}), ('type_in_app', {'app': 'Word', 'text': 'Whats up dawg'})]
    # Notepad is where Otto's notes open anyway, and an explicit note request is still a note.
    for text in ('open notepad and write "whats up dawg"', 'open word and write a note saying whats up dawg'):
        plan = compiler.compile_request(text, apps.INDEX, None)
        assert [s['do'] for s in plan.steps] == ['open_app', 'new_note'], text


@pytest.mark.parametrize('text,expected', [
    ('can you type Hello World in word?', {'app': 'word', 'text': 'Hello World'}),
    ('write "Dear Sir" into Word', {'app': 'word', 'text': 'Dear Sir'}),
    ('type hello world in note pad', None),            # stays one of Otto's notes
    ('type hello in my essay', None),                  # not an installed app
])
def test_type_in_app_rule(word_installed, text, expected):
    intent = details.type_in_app_intent(text, apps.INDEX)
    assert (intent and intent.params) == expected


def test_a_model_cannot_choose_type_in_app():
    assert registry.ACTIONS['type_in_app'].for_brain is False


# --- slice 2: click, fill and toggle by name, each with proof ----------------------------------------

@pytest.fixture
def window(monkeypatch):
    """A pretend app window whose control list the test can change when something is pressed."""
    state = N(controls=[], pressed=[], foreground=7)
    monkeypatch.setattr(app_control, 'front_window', lambda app: ({'hwnd': 7, 'title': 'Doc'}, 'Notepad', ''))
    monkeypatch.setattr(ui_probe, 'list_controls', lambda hwnd, limit=150: list(state.controls))
    monkeypatch.setattr(win, 'foreground', lambda: state.foreground)
    monkeypatch.setattr(win, 'window_info', lambda hwnd: {'title': 'Doc'})
    monkeypatch.setattr(app_control.time, 'sleep', lambda n: None)
    return state


def button(name, **extra):
    return control('Button', name, checked=None, **extra)


def test_click_is_verified_when_the_window_reacts(window, monkeypatch):
    window.controls = [button('Find'), button('Replace')]

    def press(target):
        window.pressed.append(target['name'])
        window.controls = [button('Find next'), button('Close')]        # a panel opened
        return True
    monkeypatch.setattr(ui_probe, 'press', press)
    result = apps.click_button('notepad', 'find')
    assert result.status == OutcomeStatus.VERIFIED and window.pressed == ['Find']


def test_click_that_changes_nothing_is_not_claimed(window, monkeypatch):
    window.controls = [button('Find')]
    monkeypatch.setattr(ui_probe, 'press', lambda target: True)
    assert apps.click_button('notepad', 'find').status == OutcomeStatus.UNCERTAIN


@pytest.mark.parametrize('controls,asked,phrase', [
    ([button('Save'), button('Save')], 'save', 'more than one'),                # two identical names: ask
    ([button('Open')], 'print', "can't see"),
    ([button('Delete all history')], 'history', 'full name'),                   # risky real name not asked for
])
def test_click_stops_instead_of_guessing(window, monkeypatch, controls, asked, phrase):
    window.controls = controls
    monkeypatch.setattr(ui_probe, 'press', lambda target: pytest.fail('pressed without a safe target'))
    result = apps.click_button('notepad', asked)
    assert result.status == OutcomeStatus.NEEDS_INPUT and phrase in result.say


def test_toggle_reads_the_state_back(window, monkeypatch):
    window.controls = [control('CheckBox', 'Word wrap', checked=False)]

    def flip(target):
        window.controls = [control('CheckBox', 'Word wrap', checked=True)]
        return True
    monkeypatch.setattr(ui_probe, 'flip', flip)
    assert app_control.toggle('notepad', 'word wrap', 'on').status == OutcomeStatus.VERIFIED
    # Already on: nothing is pressed.
    monkeypatch.setattr(ui_probe, 'flip', lambda target: pytest.fail('flipped a switch that was already right'))
    result = app_control.toggle('notepad', 'word wrap', 'on')
    assert result.status == OutcomeStatus.VERIFIED and 'already on' in result.say


def test_toggle_refuses_things_that_are_not_switches(window):
    window.controls = [button('Save')]
    assert "isn't an on/off switch" in app_control.toggle('notepad', 'save', 'on').say


def test_set_field_reads_back_and_refuses_private_boxes(window, monkeypatch):
    box = {}
    window.controls = [control('Edit', 'File name'), control('Edit', 'Password', password=True)]
    monkeypatch.setattr(ui_probe, 'set_value', lambda target, text: box.update(text=text) or True)
    monkeypatch.setattr(ui_probe, 'read_text', lambda target: box.get('text'))
    assert app_control.set_field('notepad', 'file name', 'essay draft').status == OutcomeStatus.VERIFIED
    box.clear()
    result = app_control.set_field('notepad', 'password', 'hunter2')
    assert result.status == OutcomeStatus.NEEDS_INPUT and 'never type' in result.say and not box


@pytest.mark.parametrize('text,action,params', [
    ('turn on word wrap in notepad', 'toggle', {'app': 'notepad', 'name': 'word wrap', 'state': 'on'}),
    ('can you untick the status bar option in Notepad?', 'toggle', {'app': 'notepad', 'name': 'status bar', 'state': 'off'}),
    ('set the file name box to Essay Draft in word', 'set_field', {'app': 'word', 'field': 'file name', 'text': 'Essay Draft'}),
    ('set volume to 30 in word', None, None),                 # still a volume request
    ('turn on the lights in the kitchen', None, None),        # not an installed app
])
def test_control_rules(word_installed, text, action, params):
    intent = details.control_intent(text, apps.INDEX)
    assert (intent and intent.action, intent and intent.params) == (action, params)


def test_risky_names_need_a_yes_and_models_cannot_choose_these():
    from core import safety
    from hands.registry import ASK
    assert safety.step_risk({'do': 'toggle', 'with': {'app': 'x', 'name': 'delete on exit', 'state': 'on'}}) == ASK
    assert safety.step_risk({'do': 'set_field', 'with': {'app': 'x', 'field': 'title', 'text': 'please send it'}}) < ASK
    assert not registry.ACTIONS['toggle'].for_brain and not registry.ACTIONS['set_field'].for_brain


# --- "what's playing" and playlists ------------------------------------------------------------------

def test_whats_playing_gives_the_answer_not_a_hedge(monkeypatch):
    from core import safety
    from hands.registry import Result
    monkeypatch.setattr(registry.ACTIONS['now_playing'], 'fn', lambda: Result(True, 'Outside by Calvin Harris.'))
    result = safety.run_plan([{'do': 'now_playing'}])
    assert result.ok and result.say == 'Outside by Calvin Harris.'


def spotify(monkeypatch, controls):
    import time
    from core.tasks import Step, Task
    from hands import media, spotify_desktop
    state = N(controls=controls, pressed=[])
    monkeypatch.setattr(app_control, 'front_window', lambda app: ({'hwnd': 1}, 'Spotify', ''))
    monkeypatch.setattr(win, 'foreground', lambda: 1)
    monkeypatch.setattr(ui_probe, 'list_controls', lambda hwnd, limit=150: list(state.controls))
    monkeypatch.setattr(media, 'sessions', lambda: [{'app': 'Spotify.exe', 'status': media.PLAYING,
                                                     'title': 'heat', 'artist': 'Cloaks'}])

    def press(target):
        state.pressed.append(target['name'])
        if target['name'] == 'My playlist #9 Kihurn':                       # the sidebar entry opens the page
            state.controls = state.controls + [button('Play My playlist #9'), button('Play heat by Cloaks')]
        elif target['name'] == 'Play My playlist #9':
            state.controls = [button('My playlist #9 Kihurn'), button('Pause My playlist #9')]
        return True
    monkeypatch.setattr(ui_probe, 'press', press)
    step = Step('s', 'play_music', {'query': '#9', 'kind': 'playlist'})
    task = Task('play', [step])
    task.cancel = N(is_set=lambda: False, wait=lambda seconds: None)
    return state, lambda: spotify_desktop.play(step, task, time.monotonic() + 45, lambda text: None)


def test_my_playlist_is_opened_from_the_library_and_played(monkeypatch):
    state, play = spotify(monkeypatch, [button('My playlist #9 Kihurn'), button('Rock Kihurn'), button('Play The Hills')])
    result = play()
    assert result.status == OutcomeStatus.VERIFIED, result.say
    assert state.pressed == ['My playlist #9 Kihurn', 'Play My playlist #9'] and 'My playlist #9' in result.say


def test_missing_or_ambiguous_playlist_presses_nothing(monkeypatch):
    state, play = spotify(monkeypatch, [button('Rock Kihurn')])
    assert play().status == OutcomeStatus.NEEDS_INPUT and state.pressed == []
    state, play = spotify(monkeypatch, [button('My playlist #9 Kihurn'), button('Playlist #9 Someone')])
    result = play()
    assert result.status == OutcomeStatus.NEEDS_INPUT and 'more than one' in result.say and state.pressed == []
