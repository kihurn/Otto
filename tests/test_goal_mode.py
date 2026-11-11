"""Goal mode: Qwen picks the next step by number from the window's real controls; Otto's code checks,
acts and re-reads. Qwen and Windows are both faked here."""
from types import SimpleNamespace as N
import pytest
from core import compiler, details, goal_mode, methods
from core.tasks import OutcomeStatus
from hands import app_control, apps, registry, ui_probe, win


@pytest.fixture(autouse=True)
def actions(monkeypatch, tmp_path):
    registry.load_all()
    monkeypatch.setattr(methods, 'METHODS_FILE', tmp_path / 'methods.json')


def control(kind, name, **extra):
    base = {'id': 0, 'name': name, 'type': kind, 'automation_id': '', 'rect': (0, 0, 100, 20), 'password': False,
            'enabled': True, 'focused': False, 'read_only': False, 'checked': None, 'element': N(SetFocus=lambda: None)}
    return dict(base, **extra)


@pytest.fixture
def app(monkeypatch):
    """A pretend app. `screens` maps a pressed button name to the controls shown afterwards."""
    state = N(controls=[], screens={}, pressed=[], typed=[], text='', asked=0)
    monkeypatch.setattr(app_control, 'front_window', lambda name: ({'hwnd': 7, 'title': 'App'}, 'Word', ''))
    monkeypatch.setattr(ui_probe, 'list_controls', lambda hwnd, limit=150: list(state.controls))
    monkeypatch.setattr(ui_probe, 'read_text', lambda target: state.text)
    monkeypatch.setattr(win, 'foreground', lambda: 7)
    monkeypatch.setattr(win, 'window_info', lambda hwnd: {'title': 'App', 'rect': (0, 0, 10, 10)})
    monkeypatch.setattr(win, 'focused_is_password', lambda: False)
    monkeypatch.setattr(goal_mode.time, 'sleep', lambda n: None)

    def press(target):
        state.pressed.append(target['name'])
        if target['name'] in state.screens:
            state.controls = state.screens[target['name']]
        return True

    def type_text(text):
        state.typed.append(text)
        state.text += text
    monkeypatch.setattr(ui_probe, 'press', press)
    monkeypatch.setattr(win, 'type_text', type_text)
    return state


def qwen(app, *picks):
    """A scripted Qwen: each pick is (action, control name). Names are turned into the numbers it was shown."""
    picks = list(picks)

    def propose(prompt, image, deadline):
        app.asked += 1
        action, name = picks.pop(0) if picks else ('stop', '')
        shown = goal_mode.shortlist(app.controls)
        number = next((c['id'] for c in shown if c['name'] == name), 0)
        return {'action': action, 'id': number, 'why': 'test'}
    return propose


def test_word_start_screen_then_types_the_users_words(app):
    app.controls = [control('ListItem', 'Blank document'), control('Button', 'Open')]
    app.screens = {'Blank document': [control('Document', 'Page 1', focused=True)]}
    result = goal_mode.pursue('word', 'get somewhere to type', text='hello there',
                              propose=qwen(app, ('click', 'Blank document')))
    assert result.status == OutcomeStatus.VERIFIED and app.typed == ['hello there']
    assert app.asked == 1                      # the typing itself needed no model
    assert result.data['learned'] == {'app': 'Word', 'goal': 'get somewhere to type', 'steps': ['Blank document']}


def test_save_is_found_inside_the_file_menu(app):
    app.controls = [control('MenuItem', 'File'), control('MenuItem', 'Edit')]
    app.screens = {'File': [control('MenuItem', 'File'), control('MenuItem', 'Save'), control('MenuItem', 'Print')],
                   'Save': [control('Edit', 'File name')]}
    result = goal_mode.pursue('notepad', 'press save', target_name='save',
                              propose=qwen(app, ('click', 'File'), ('click', 'Save')))
    assert result.status == OutcomeStatus.VERIFIED and app.pressed == ['File', 'Save']
    assert result.data['judged_by'] == 'code'


def test_unsure_model_means_otto_asks(app):
    app.controls = [control('Button', 'Mystery')]
    result = goal_mode.pursue('word', 'export as pdf', propose=qwen(app, ('stop', '')))
    assert result.status == OutcomeStatus.NEEDS_INPUT and 'next step' in result.say and app.pressed == []


def test_done_with_nothing_done_is_not_believed(app):
    app.controls = [control('Button', 'Mystery')]
    assert goal_mode.pursue('word', 'export as pdf', propose=qwen(app, ('done', ''))).status == OutcomeStatus.NEEDS_INPUT


@pytest.mark.parametrize('name', ['Delete all', 'Send', 'Sign out'])
def test_risky_buttons_are_never_pressed_from_goal_mode(app, name):
    app.controls = [control('Button', name)]
    result = goal_mode.pursue('word', 'tidy up', propose=qwen(app, ('click', name)))
    assert result.status == OutcomeStatus.NEEDS_INPUT and 'by name' in result.say and app.pressed == []


def test_a_made_up_number_or_bad_action_is_rejected(app):
    app.controls = [control('Button', 'OK')]
    shown = goal_mode.shortlist(app.controls)
    for reply in ({'action': 'click', 'id': 99}, {'action': 'run', 'id': 1}, {'action': 'type', 'id': 1}, 'click 1'):
        with pytest.raises(ValueError):
            goal_mode.validate(reply, shown, can_type=False)
    assert goal_mode.validate({'action': 'click', 'id': 1}, shown, can_type=False)[1]['name'] == 'OK'


def test_private_boxes_are_refused_even_if_the_model_picks_them(app):
    app.controls = [control('Edit', 'Password', password=True), control('Edit', 'Notes')]
    result = goal_mode.pursue('word', 'fill in', text='hunter2', propose=qwen(app, ('type', 'Password')))
    assert result.status == OutcomeStatus.NEEDS_INPUT and app.typed == []


def test_pressing_things_that_change_nothing_stops_after_two(app):
    app.controls = [control('Button', 'Dead')]
    result = goal_mode.pursue('word', 'do a thing', propose=qwen(app, *[('click', 'Dead')] * 6))
    assert result.status == OutcomeStatus.NEEDS_INPUT and app.pressed == ['Dead']


def test_saved_method_replays_without_the_model_and_retires_after_two_misses(app):
    methods.save('Word', 'press save', ['File', 'Save'])
    start = [control('MenuItem', 'File')]
    app.controls = list(start)
    app.screens = {'File': [control('MenuItem', 'Save')], 'Save': [control('Edit', 'File name')]}
    result = goal_mode.pursue('word', 'press save', target_name='Save', propose=qwen(app))
    assert result.status == OutcomeStatus.VERIFIED and app.pressed == ['File', 'Save'] and app.asked == 0
    assert 'learned' not in result.data          # nothing new to offer to save
    # The app changes and the saved names are gone: two misses retire the method.
    for _ in range(2):
        app.controls = [control('Button', 'Something else')]
        goal_mode.pursue('word', 'press save', propose=qwen(app, ('stop', '')))
    assert methods.find('Word', 'press save') is None


def test_prompt_lists_real_controls_and_no_typed_text(app):
    shown = goal_mode.shortlist([control('CheckBox', 'Word wrap', checked=True), control('Button', '')])
    prompt = goal_mode.build_prompt('turn it off', 'Notepad', shown, ['pressed "View" (changed the window)'], False)
    assert "1 | CheckBox | 'Word wrap' | on" in prompt and '"type"' not in prompt and len(shown) == 1


# --- the words and the wiring ------------------------------------------------------------------------

@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setattr(apps.INDEX, 'match_exact', lambda name: name in {'word', 'notepad'}, raising=False)


def test_app_named_once_applies_to_every_click(installed):
    for text in ('click view then click status in notepad', 'click "view" then click "status" in notepad'):
        plan = compiler.compile_request(text, apps.INDEX, None)
        assert [(s['do'], s['with']) for s in plan.steps] == [
            ('click_button', {'app': 'notepad', 'button': 'view'}),
            ('click_button', {'app': 'notepad', 'button': 'status'})], text


@pytest.mark.parametrize('text,expected', [
    ('export this as a pdf in word', {'app': 'word', 'goal': 'export this as a pdf'}),
    ('open the report in word', None),               # opening things has its own rules
    ('what is the weather in kuala lumpur', None),   # not an installed app
])
def test_anything_else_in_an_app_becomes_a_goal(installed, text, expected):
    intent = details.app_goal_intent(text, apps.INDEX)
    assert (intent and intent.params) == expected


def test_goal_mode_only_runs_for_live_requests(app):
    # Called directly (as tests and dry runs do) there is no live task, so the plain answer comes back.
    app.controls = [control('Button', 'Blank document')]
    result = app_control.type_in_app('word', 'hello')
    assert result.status == OutcomeStatus.NEEDS_INPUT and app.pressed == []


def test_goals_that_mention_risky_words_need_a_yes_and_models_cannot_pick_goal_mode():
    from core import safety
    from hands.registry import ASK
    assert safety.step_risk({'do': 'app_goal', 'with': {'app': 'word', 'goal': 'delete the first page'}}) == ASK
    assert safety.step_risk({'do': 'app_goal', 'with': {'app': 'word', 'goal': 'make the title bold'}}) < ASK
    assert registry.ACTIONS['app_goal'].for_brain is False
