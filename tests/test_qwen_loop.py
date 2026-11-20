"""Qwen in the loop: the interpreter (what does this request mean, given the conversation?), the supervisor
(that didn't work, what now?), misheard names, and the fixed voice phrases. Qwen is faked throughout."""
from types import SimpleNamespace as N
import pytest

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













# --- inside the pipeline (dry run, fake Laya) --------------------------------------------------------







def test_quiet_save_that_is_accepted_but_a_quiet_yes_is_not(otto):
    otto.handle('close discord')                       # leaves a "should I close Discord?" question open
    assert otto.pending is not None
    assert 'repeat your answer' in otto.handle('yes', heard_conf=-1.2).text
    # While a yes would approve something, a quiet "save that" is no exception (Codex review 19 Nov: "okay save
    # that" also reads as yes). With nothing waiting for a yes, it is still accepted.
    assert 'repeat your answer' in otto.handle('okay save that', heard_conf=-1.2).text
    otto.handle('no')
    assert otto.pending is None
    assert 'repeat your answer' not in otto.handle('save that', heard_conf=-1.2).text


# --- the supervisor ----------------------------------------------------------------------------------





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
