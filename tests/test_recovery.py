import pytest
from core.recovery import validate
from core.details import _media


@pytest.mark.parametrize('bad', [None, {}, {'version': True, 'snapshot_id': 's', 'candidate_id': 0},
    {'version': 1, 'snapshot_id': 'old', 'candidate_id': 0},
    {'version': 1, 'snapshot_id': 's', 'candidate_id': -1},
    {'version': 1, 'snapshot_id': 's', 'candidate_id': 0, 'shell': 'bad'}])
def test_proposal_rejected(bad):
    with pytest.raises(ValueError):
        validate(bad, 's', {0})


def test_candidate_id_is_snapshot_bound():
    assert validate({'version': 1, 'snapshot_id': 's', 'candidate_id': 2}, 's', {2}) == 2


def test_spoken_volume_amounts():
    assert _media('lower the volume by five').params == {'step': -5}
    assert _media('increase the volume to seventy').params == {'level': 70}
    assert _media('lower the volume by thirty two').params == {'step': -32}
    assert _media('set volume to thirty-two').params == {'level': 32}


def test_disabled_recovery_has_no_capture(monkeypatch):
    from core import recovery, config
    monkeypatch.setattr(config, 'load_settings', lambda: {'recovery': {'enabled': False}})
    monkeypatch.setattr(recovery, 'capture', lambda *a: pytest.fail('capture while disabled'))
    assert not recovery.recover(1, 'focus_spotify_search')


@pytest.mark.parametrize('change', ['none', 'window', 'cancel'])
def test_qwen_candidate_rechecked_before_focus(monkeypatch, change):
    import sys, re, time
    from types import SimpleNamespace as N
    from core import recovery, config, brain
    from core.tasks import Task, Step
    from core.action_runtime import current, ActionInterrupted
    focused = []
    ctrl = N(window_text=lambda: 'Search', is_visible=lambda: True, is_enabled=lambda: True,
             rectangle=lambda: (0, 0, 100, 20), set_focus=lambda: focused.append(True),
             element_info=N(element=N(CurrentIsPassword=False)))
    dialog = N(descendants=lambda **kw: [ctrl])
    monkeypatch.setitem(sys.modules, 'pywinauto', N(Application=lambda **kw: N(connect=lambda **kw: N(window=lambda **kw: dialog))))
    monkeypatch.setattr(config, 'load_settings', lambda: {'recovery': {'enabled': True}})
    monkeypatch.setattr(recovery, 'capture', lambda hwnd: ('target', 'fake_jpeg'))
    monkeypatch.setattr(recovery, 'identity', lambda hwnd: 'changed' if change == 'window' else 'target')
    task = Task('search', [Step('s0', 'search_in_app', {})])
    def ask(job, prompt, **kw):
        assert kw['images'] == ['fake_jpeg']
        if change == 'cancel':
            task.cancel.set()
        return N(data={'version': 1, 'snapshot_id': re.search(r'"snapshot_id":"([^"]+)"', prompt)[1], 'candidate_id': 0})
    monkeypatch.setattr(brain, 'Brain', lambda settings: N(ask=ask))
    token = current.set((task, 1, time.monotonic()+45))
    try:
        if change == 'cancel':
            with pytest.raises(ActionInterrupted):
                recovery.recover(1, 'focus_spotify_search')
        else:
            assert recovery.recover(1, 'focus_spotify_search') == (change == 'none')
        assert focused == ([True] if change == 'none' else [])
        assert task.recoveries == {'s0': 1}
    finally:
        current.reset(token)
