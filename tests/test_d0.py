import time
import pytest
from core.audio_context import VolumeContext
from core import safety
from core.tasks import Task, Step
from hands import registry


def test_endpoint_and_expiry_invalidate_volume():
    context = VolumeContext()
    context.bind('speakers')
    assert context.resolve('increase it up to 70', 'speakers') == 'increase the volume up to 70'
    assert context.resolve('lower it to 30', 'headset') is None
    context.bind('speakers')
    context.updated -= 121
    assert context.resolve('what is it now', 'speakers') is None


@pytest.mark.parametrize('mode', ['cancel', 'revise', 'expire'])
def test_interruption_during_progress_prevents_dispatch(monkeypatch, mode):
    registry.load_all()
    task = Task('volume', [Step('s0', 'set_volume', {'level': 30}), Step('s1', 'set_volume', {'level': 20})])
    def progress(message):
        if mode == 'cancel':
            task.cancel.set()
        elif mode == 'revise':
            task.revision += 1
        else:
            time.sleep(0.02)
    if mode == 'expire':
        task.deadline_at = time.monotonic() + .01
    monkeypatch.setattr(registry.ACTIONS['set_volume'], 'fn', lambda **kw: pytest.fail('late dispatch'))
    result = safety.run_plan([{'do': 'set_volume', 'with': s.args} for s in task.steps], task=task, progress=progress)
    assert not result.ok


def test_read_risk_does_not_imply_verification(monkeypatch):
    registry.load_all()
    monkeypatch.setattr(registry.ACTIONS['time_left'], 'fn', lambda: registry.Result(True, 'read accepted'))
    result = safety.run_plan([{'do': 'time_left'}])
    assert not result.ok and result.data['outcome_status'] == 'dispatched'


def test_delayed_spotify_focus_is_polled(monkeypatch):
    from hands import spotify_search as search, win
    states = iter([('not_editable', {}), ('search_label_missing', {}), ('ready', {})])
    monkeypatch.setattr(search, 'field_state', lambda hwnd: next(states, ('ready', {})))
    monkeypatch.setattr(search.time, 'sleep', lambda n: None)
    typed = []
    monkeypatch.setattr(win, 'hotkey', lambda *a: None)
    monkeypatch.setattr(win, 'type_text', typed.append)
    assert search.search(1, 'the hills').ok and typed == ['the hills']


def test_focus_loss_after_select_all_stops_typing(monkeypatch):
    from hands import spotify_search as search, win
    states = iter([('ready', {}), ('ready', {}), ('focus_lost', {})])
    monkeypatch.setattr(search, 'field_state', lambda hwnd: next(states))
    monkeypatch.setattr(win, 'hotkey', lambda *a: None)
    monkeypatch.setattr(win, 'type_text', lambda *a: pytest.fail('wrong-window typing'))
    result = search.search(1, 'the hills')
    assert not result.ok and result.data['error_code'] == 'focus_lost'


def test_spotify_named_combobox_without_global_focus_guess(monkeypatch):
    import sys
    from types import SimpleNamespace as N
    from hands import spotify_search as search, win
    value = N(CurrentIsReadOnly=False, CurrentValue='')
    value.SetValue = lambda query: setattr(value, 'CurrentValue', query)
    control = N(window_text=lambda: 'What do you want to play?', is_visible=lambda: True,
                is_enabled=lambda: True, element_info=N(element=N(CurrentIsPassword=False)),
                iface_value=value, set_focus=lambda: None, has_keyboard_focus=lambda: False)
    dialog = N(descendants=lambda **kw: [control])
    monkeypatch.setitem(sys.modules, 'pywinauto', N(Application=lambda **kw: N(connect=lambda **kw: N(window=lambda **kw: dialog))))
    monkeypatch.setattr(win, 'foreground', lambda: 7)
    monkeypatch.setattr(win, 'hotkey', lambda *a: pytest.fail('unverified global keystroke'))
    assert search.search(7, 'The Hills The Weeknd').ok
    assert value.CurrentValue == 'The Hills The Weeknd'
