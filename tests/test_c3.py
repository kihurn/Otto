"""Task boundaries and observations, with no desktop effects."""
import time
from types import SimpleNamespace
import pytest
from core import compiler, planner, safety
from core.details import Intent, _media
from core.tasks import Task, Step, Outcome, OutcomeStatus, Evidence
from hands import apps, registry, media


@pytest.fixture(autouse=True)
def actions():
    registry.load_all()


@pytest.mark.parametrize('text,action,params', [
    ('Could you lower the volume down to 30?', 'set_volume', {'level': 30}),
    ('lower down the volume', 'volume_down', {'step': -10}),
    ('What is the volume now?', 'get_volume', {}),
])
def test_volume_rules(text, action, params):
    intent = _media(text)
    assert (intent.action, intent.params) == (action, params)


def test_volume_read_never_writes(monkeypatch):
    monkeypatch.setattr(media, 'current_volume', lambda: 52)
    monkeypatch.setattr(media, '_endpoint', lambda: pytest.fail('read must not write'))
    result = safety.run_plan([{'do': 'get_volume'}])
    assert result.ok and result.data['volume'] == 52


def test_quotes_preserved_in_compiler():
    assert compiler.clauses('play "Then and Now", then set a timer for 2 minutes') == [
        'play "Then and Now"', 'set a timer for 2 minutes']


def test_invalid_final_step_no_effects(monkeypatch):
    monkeypatch.setattr(registry.ACTIONS['open_app'], 'fn', lambda **kw: pytest.fail('effect'))
    plan = compiler.compile_request('open Discord then set volume to 101', apps.INDEX, None)
    assert plan.error


@pytest.mark.parametrize('status', [OutcomeStatus.UNCERTAIN, OutcomeStatus.FAILED, OutcomeStatus.NEEDS_INPUT])
def test_non_success_stops_dependencies(monkeypatch, status):
    monkeypatch.setattr(registry.ACTIONS['get_volume'], 'fn', lambda: Outcome(status, 'stopped'))
    monkeypatch.setattr(registry.ACTIONS['set_volume'], 'fn', lambda **kw: pytest.fail('dependent effect'))
    assert not safety.run_plan([{'do': 'get_volume'}, {'do': 'set_volume', 'with': {'level': 30}}]).ok


def test_verified_backward_reference(monkeypatch):
    monkeypatch.setattr(media, 'current_volume', lambda: 30)
    calls = []
    monkeypatch.setattr(registry.ACTIONS['set_volume'], 'fn', lambda level: (calls.append(level) or registry.Result(True, 'set')))
    result = safety.run_plan([{'id': 'observed', 'do': 'get_volume'},
                              {'do': 'set_volume', 'with': {'level': {'$ref': 'observed.volume'}}}])
    assert result.ok and calls == [30]


def test_forward_reference_rejected():
    with pytest.raises(registry.InvalidPlan):
        planner.validate_steps([{'do': 'set_volume', 'with': {'level': {'$ref': 'later.volume'}}},
                                {'id': 'later', 'do': 'get_volume'}])


def test_simulated_reference_never_executes(monkeypatch):
    monkeypatch.setattr(registry.ACTIONS['set_volume'], 'fn', lambda **kw: pytest.fail('effect'))
    result = safety.run_plan([{'id': 'reading', 'do': 'get_volume'},
                              {'do': 'set_volume', 'with': {'level': {'$ref': 'reading.volume'}}}], dry_run=True)
    assert not result.ok and result.data['outcome_status'] == 'simulated'


def test_cancel_during_action_discards_late_success(monkeypatch):
    task = Task('read', [Step('s0', 'get_volume', {})])
    def late():
        task.cancel.set()
        return registry.Result(True, 'volume', {'volume': 30})
    monkeypatch.setattr(registry.ACTIONS['get_volume'], 'fn', late)
    result = safety.run_plan([{'do': 'get_volume'}], task=task)
    assert result.data['outcome_status'] == 'cancelled'


def test_card_play_bound_to_artist():
    from hands.spotify_desktop import play_candidates
    def candidate(artist):
        parent = SimpleNamespace(rectangle=lambda: SimpleNamespace(width=lambda: 900, height=lambda: 100),
                                 descendants=lambda **kw: [SimpleNamespace(window_text=lambda: 'Over the Moon ' + artist)]
                                 if kw['control_type'] == 'Text' else [], parent=lambda: None)
        return SimpleNamespace(window_text=lambda: 'Play', is_visible=lambda: True,
                               is_enabled=lambda: True, parent=lambda: parent)
    good, bad = candidate('The Marías'), candidate('Other Artist')
    # A nonmatching card's parent is inaccessible: real scanning must skip, not click it.
    dialog = SimpleNamespace(descendants=lambda **kw: [good])
    assert play_candidates(dialog, 'Over the Moon', 'The Marias') == [good]
    dialog = SimpleNamespace(descendants=lambda **kw: [bad])
    assert play_candidates(dialog, 'Over the Moon', 'The Marias') == []


@pytest.mark.parametrize('field_name,should_type', [('Search', True), ('Message', False)])
def test_spotify_types_literal_spaces_only_in_search(monkeypatch, field_name, should_type):
    import sys
    from hands import win
    monkeypatch.setattr(win, 'IS_WINDOWS', True)
    monkeypatch.setattr(apps, 'open_app', lambda *a: registry.Result(True, 'opened'))
    monkeypatch.setattr(win, 'find_window', lambda *a: {'hwnd': 1})
    monkeypatch.setattr(win, 'focus', lambda *a: True)
    monkeypatch.setattr(win, 'foreground', lambda: 1)
    monkeypatch.setattr(win, 'hotkey', lambda *a: None)
    typed = []
    monkeypatch.setattr(win, 'type_text', typed.append)
    monkeypatch.setattr(apps.time, 'sleep', lambda *a: None)
    field = SimpleNamespace(CurrentControlType=50004, CurrentIsPassword=False, CurrentName=field_name)
    monkeypatch.setitem(sys.modules, 'pywinauto.uia_defines', SimpleNamespace(IUIA=lambda: SimpleNamespace(get_focused_element=lambda: field)))
    result = apps.search_in_app('Spotify', 'the hills by the weeknd')
    assert result.ok == should_type
    assert typed == (['the hills by the weeknd'] if should_type else [])
