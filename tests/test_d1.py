import pytest
from core.details import _media
from hands import audio_devices as audio, notes, timers


class AudioProvider:
    def __init__(self):
        self.active = {'speaker':'Speakers (USB)', 'headset':'Headphones', 'second':'Speakers (HDMI)'}
        self.roles = {0:'headset', 1:'headset'}
        self.calls = []
    def inventory(self):
        return dict(self.active)
    def defaults(self):
        return dict(self.roles)
    def set(self, endpoint, role):
        self.calls.append((endpoint, role))
        self.roles[role] = endpoint


@pytest.fixture
def provider(monkeypatch):
    value = AudioProvider()
    monkeypatch.setattr(audio, 'WindowsAudioOutputs', lambda: value)
    monkeypatch.setattr(audio, '_receipt', None)
    return value


def test_unique_device_switch_and_verified_undo(provider):
    assert audio.set_output('Speakers (USB)').ok
    assert provider.roles == {0:'speaker', 1:'speaker'}
    assert audio.undo_output().ok
    assert provider.roles == {0:'headset', 1:'headset'}


def test_ambiguous_device_does_not_switch(provider):
    result = audio.set_output('speakers')
    assert len(result.data['audio_candidates']) == 2 and not provider.calls
    assert audio.set_output_id('second').ok


def test_undo_does_not_overwrite_manual_switch(provider):
    assert audio.set_output_id('speaker').ok
    provider.roles[1] = 'second'
    assert not audio.undo_output().ok
    assert provider.roles == {0:'speaker', 1:'second'}


def test_disconnected_output_does_not_dispatch(provider):
    del provider.active['speaker']
    assert not audio.set_output_id('speaker').ok and not provider.calls


def test_output_phrase_uses_named_action():
    intent = _media('can you make my speakers as the default output')
    assert intent.action == 'set_audio_output' and intent.params == {'device':'speakers'}


def test_duplicate_note_name_does_not_overwrite(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, 'NOTES', tmp_path)
    monkeypatch.setattr(notes, '_last', {})
    monkeypatch.setattr(notes.subprocess, 'Popen', lambda *a: None)
    first = notes.new_note('first', 'same')
    second = notes.new_note('second', 'same')
    assert first.ok and second.ok and first.data['path'] != second.data['path']
    assert sorted(p.read_text().strip() for p in tmp_path.glob('*.txt')) == ['first','second']


def test_timer_has_readback_before_success():
    result = timers.set_timer(60)
    try:
        assert result.ok and result.data['timer_id'] in timers._timers
    finally:
        timers.cancel_timers()


def test_similarly_named_playlist_is_not_a_matching_song():
    from types import SimpleNamespace
    from hands.spotify_desktop import play_candidates
    playlist = SimpleNamespace(window_text=lambda: 'Play The Weeknd — The Hills',
                               is_visible=lambda: True, is_enabled=lambda: True)
    dialog = SimpleNamespace(descendants=lambda **kw: [playlist])
    assert play_candidates(dialog, 'The Hills', 'The Weeknd') == []


def test_swap_goes_to_the_output_that_is_not_playing(provider):
    del provider.active['second']                       # two outputs: headphones (playing) and speakers
    result = audio.swap_output()
    assert result.ok and provider.roles == {0: 'speaker', 1: 'speaker'} and 'Speakers (USB)' in result.say
    assert audio.undo_output().ok and provider.roles == {0: 'headset', 1: 'headset'}


def test_swap_with_three_outputs_asks_which_without_the_current_one(provider):
    result = audio.swap_output()
    assert not result.ok and 'Headphones' not in result.say and 'Speakers (USB)' in result.say


def test_setting_the_current_output_says_nothing_changed(provider):
    result = audio.set_output('Headphones')
    assert result.ok and 'already' in result.say
