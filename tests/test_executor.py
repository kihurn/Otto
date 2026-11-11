"""Spotify acceptance uses fake observations, never a live account."""
from types import SimpleNamespace
import io
import urllib.error
import pytest
from core import executor, safety
from core.tasks import Task, Step, TaskStatus
from hands import registry, media
from connectors import spotify as sp


@pytest.fixture
def backend(monkeypatch):
    registry.load_all()
    monkeypatch.setattr(media, '_spotify', lambda: sp)
    monkeypatch.setattr(media, '_launch_spotify', lambda: None)
    monkeypatch.setattr(sp, 'best_match', lambda **kw: ('track', 'spotify:track:new', {'name': 'The Hills', 'artists': [{'name': 'The Weeknd'}]}))
    monkeypatch.setattr(sp, 'ensure_device', lambda launch: {'id': 'pc'})
    calls = []
    monkeypatch.setattr(sp, 'play', lambda *args: calls.append(args))
    state = {'item': {'uri': 'spotify:track:new'}, 'device': {'id': 'pc'}, 'is_playing': True}
    monkeypatch.setattr(sp, '_call', lambda *a, **k: state)
    return calls, state


def run(task=None, dry_run=False):
    return safety.run_plan([{'do': 'play_music', 'with': {'query': 'The Hills'}}], task=task, dry_run=dry_run)


def test_verified_track_and_evidence(backend):
    task = Task('play', [Step('s0', 'play_music', {'query': 'The Hills'})])
    result = run(task)
    assert result.ok and task.status == TaskStatus.SUCCEEDED
    assert task.results['s0'].evidence[0].observed['device_id'] == 'pc'
    assert len(backend[0]) == 1


@pytest.mark.parametrize('change', [{'item': {'uri': 'old'}}, {'device': {'id': 'phone'}}, {'is_playing': None}, {'item': None}])
def test_wrong_or_missing_state_never_claims_success(backend, monkeypatch, change):
    backend[1].update(change)
    ticks = iter(range(0, 200, 2))
    monkeypatch.setattr(executor.time, 'monotonic', lambda: next(ticks))
    task = Task('play', [Step('s0', 'play_music', {'query': 'The Hills'})])
    monkeypatch.setattr(task.cancel, 'wait', lambda timeout: False)
    result = run(task)
    assert not result.ok and result.data['outcome_status'] == 'uncertain'
    assert len(backend[0]) == 1


def test_relinked_track(backend):
    backend[1]['item'] = {'uri': 'relinked', 'linked_from': {'uri': 'spotify:track:new'}}
    assert run().ok


def test_simulation_has_no_backend_calls(backend, monkeypatch):
    monkeypatch.setattr(sp, 'best_match', lambda **kw: pytest.fail('simulation must not search'))
    result = run(dry_run=True)
    assert not result.ok and result.data['outcome_status'] == 'simulated' and backend[0] == []


def test_cancel_before_dispatch(backend):
    task = Task('play', [Step('s0', 'play_music', {'query': 'The Hills'})])
    task.cancel.set()
    assert run(task).data['outcome_status'] == 'cancelled'
    assert backend[0] == []


def test_timeout_after_dispatch_observes_without_retry(backend, monkeypatch):
    def sent(*args):
        backend[0].append(args)
        raise TimeoutError()
    monkeypatch.setattr(sp, 'play', sent)
    assert run().ok and len(backend[0]) == 1


def test_delayed_observation_one_dispatch(backend, monkeypatch):
    states = iter([{}, backend[1]])
    monkeypatch.setattr(sp, '_call', lambda *a, **kw: next(states))
    task = Task('play', [Step('s0', 'play_music', {'query': 'The Hills'})])
    monkeypatch.setattr(task.cancel, 'wait', lambda seconds: False)
    assert run(task).ok and len(backend[0]) == 1


def test_cancel_during_observation_blocks_late_success(backend, monkeypatch):
    task = Task('play', [Step('s0', 'play_music', {'query': 'The Hills'})])
    def observe(*a, **kw):
        task.cancel.set()
        return backend[1]
    monkeypatch.setattr(sp, '_call', observe)
    assert run(task).data['outcome_status'] == 'cancelled'


def test_evaluation_never_dispatches(backend):
    task = Task('play', [Step('s0', 'play_music', {'query': 'The Hills'})], mode='evaluation')
    assert run(task).data['outcome_status'] == 'simulated' and backend[0] == []


def test_liked_tracks_verified(backend, monkeypatch):
    calls = []
    def call(method, path, *args):
        calls.append((method, path))
        if path == '/me/tracks':
            return {'items': [{'track': {'uri': 'spotify:track:new'}}]}
        return backend[1] if method == 'GET' else None
    monkeypatch.setattr(sp, '_call', call)
    result = safety.run_plan([{'do': 'play_liked', 'with': {}}])
    assert result.ok and calls.count(('PUT', '/me/player/play')) == 1


def test_local_device_preferred_over_active_phone(monkeypatch):
    monkeypatch.setenv('COMPUTERNAME', 'my-pc')
    monkeypatch.setattr(sp.config, 'load_settings', lambda: {})
    monkeypatch.setattr(sp, 'devices', lambda: [{'id': 'phone', 'type': 'Smartphone', 'is_active': True},
                                               {'id': 'pc', 'type': 'Computer', 'name': 'my-pc'}])
    assert sp._pick_device()['id'] == 'pc'


def test_opens_desktop_even_when_device_is_listed(backend, monkeypatch):
    opened = []
    monkeypatch.setattr(media, '_launch_spotify', lambda: opened.append(True))
    assert run().ok and opened == [True]


def test_search_uri_preserves_complete_query():
    from hands.apps import builtin_search_link
    assert builtin_search_link('Spotify', 'the hills by the weeknd') == 'spotify:search:the%20hills%20by%20the%20weeknd'


def test_failed_music_stops_next_effect(backend, monkeypatch):
    monkeypatch.setattr(sp, 'best_match', lambda **kw: None)
    monkeypatch.setattr(registry.ACTIONS['set_timer'], 'fn', lambda **kw: pytest.fail('dependent effect'))
    result = safety.run_plan([{'do': 'play_music', 'with': {'query': 'x'}},
                              {'do': 'set_timer', 'with': {'seconds': 20}}])
    assert not result.ok


@pytest.mark.parametrize('body,status,ok', [(b'', 204, True), (b'204 success', 200, False), (b'[]', 200, False)])
def test_connector_response_boundary(monkeypatch, body, status, ok):
    monkeypatch.setattr(sp, '_access_token', lambda: 'fake')
    class Response(io.BytesIO):
        headers = {'Content-Type': 'application/json'}
    response = Response(body)
    response.status = status
    monkeypatch.setattr(sp.urllib.request, 'urlopen', lambda *a, **k: response)
    if ok:
        assert sp._call('PUT', '/me/player/play') is None
    else:
        with pytest.raises(sp.SpotifyError):
            sp._call('PUT', '/me/player/play')
