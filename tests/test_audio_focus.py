import pytest
from core.audio_focus import SessionCaps


class Volume:
    def __init__(self, level, mute=False):
        self.level = level
        self.mute = mute
    def GetMasterVolume(self):
        return self.level
    def GetMute(self):
        return self.mute
    def SetMasterVolume(self, level, context):
        self.level = level


class Sessions:
    def __init__(self):
        self.endpoint = 'speakers'
        self.loud = Volume(.8)
        self.quiet = Volume(.1)
        self.muted = Volume(.9, True)
        self.headphones = Volume(.65)
        self.sessions = {'loud':('speakers',self.loud), 'quiet':('speakers',self.quiet),
                         'muted':('speakers',self.muted), 'headphones':('headphones',self.headphones)}
    def snapshot(self):
        return self.endpoint, self.sessions


def test_duck_and_restore_only_loud_sessions(tmp_path):
    audio = Sessions()
    caps = SessionCaps(audio, .2, tmp_path/'journal.json')
    caps.update(True)
    assert [v.level for v in (audio.loud,audio.quiet,audio.muted,audio.headphones)] == [.2,.1,.9,.65]
    caps.update(False)
    assert audio.loud.level == .8 and audio.muted.mute


def test_manual_volume_change_is_respected(tmp_path):
    audio = Sessions()
    caps = SessionCaps(audio, .2, tmp_path/'journal.json')
    caps.update(True)
    audio.loud.level = .55
    caps.update(True)
    caps.update(False)
    assert audio.loud.level == .55


def test_endpoint_switch_restores_old_caps_new(tmp_path):
    audio = Sessions()
    caps = SessionCaps(audio, .2, tmp_path/'journal.json')
    caps.update(True)
    audio.endpoint = 'headphones'
    caps.update(True)
    assert audio.loud.level == .8 and audio.headphones.level == .2
    caps.update(False)
    assert audio.headphones.level == .65


def test_recovery_checks_instance_and_value(tmp_path):
    audio = Sessions()
    path = tmp_path/'journal.json'
    SessionCaps(audio, .2, path).update(True)
    SessionCaps(audio, .2, path).recover()
    assert audio.loud.level == .8


def test_session_arrives_during_interaction(tmp_path):
    audio = Sessions()
    caps = SessionCaps(audio, .2, tmp_path/'journal.json')
    caps.update(True)
    newcomer = Volume(.7)
    audio.sessions['new'] = ('speakers', newcomer)
    caps.update(True)
    assert newcomer.level == .2
    caps.update(False)
    assert newcomer.level == .7
