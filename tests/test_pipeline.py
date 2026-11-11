"""Whole conversations in dry-run, with a fake Laya and a fake brain."""

import pytest

from core import config
from core.brain import BrainReply

FIRST_WORD_AREA = {"play": "media", "open": "apps", "set": "timer", "find": "files", "pause": "media",
                   "turn": "media", "google": "web", "close": "apps", "thanks": "chitchat", "search": "apps",
                   "valorant": "apps", "chuck": "media"}


@pytest.fixture
def otto(monkeypatch):
    from core.pipeline import Otto
    o = Otto(config.load_settings(), dry_run=True, say=lambda s: None)
    probs = {"valorant": 0.6, "chuck": 0.2}

    def predict(t):
        w = t.lower().split()[0].strip(",?")
        area = FIRST_WORD_AREA.get(w, "unsure")
        return {"area": area, "prob": probs.get(w, 0.95), "top": [], "ms": 1}

    o.router.predict = predict
    o.router.note_new_example = lambda say=None: None

    def ask(job, prompt, system=None, images=None, want_json=False, required=(), timeout=None):
        if "Split it" in prompt:
            return BrainReply("", {"steps": ["open discord", "set a timer for 20 minutes"]}, "gemma", 0.1)
        if "Rewrite the user's latest" in prompt:
            return BrainReply("", {"request": "find a file called student resume"}, "qwen", 0.1)
        if '"area"' in prompt:
            return BrainReply("", {"area": "apps", "question": "Play chill music on Spotify?"}, "gemma", 0.1)
        if "building blocks" in prompt:
            return BrainReply("", {"steps": [{"do": "open_app", "with": {"app": "Discord"}},
                                             {"do": "hotkey", "with": {"keys": "ctrl+k"}},
                                             {"do": "type_text", "with": {"text": "taylor swift"}}]}, "gemma", 0.1)
        return BrainReply("Anytime!", {"action": "none"}, "qwen", 0.1)

    o.brain.ask = ask
    return o


def say(o, text):
    return o.handle(text).text


def test_high_zone_acts(otto):
    assert "would open Spotify" in say(otto, "Otto, open Spotify")


def test_volume_followup_reads_without_inventing_level(otto):
    say(otto, 'lower down the volume')
    assert 'check the current volume' in say(otto, 'What is it now?')
    assert 'set the volume to 30' in say(otto, 'Could you lower the volume down to 30?')


def test_d0_volume_pronouns_keep_absolute_targets(otto):
    say(otto, 'set volume to 30')
    assert 'set the volume to 70' in say(otto, 'Could you increase it up to 70?')
    assert 'turn it down' in say(otto, 'lower it by 5')
    assert otto.last['plan'].steps[0]['with']['step'] == -5
    assert 'check the current volume' in say(otto, 'what is it now')


def test_d0_unrelated_topic_clears_volume_reference(otto):
    say(otto, 'set volume to 30')
    say(otto, 'open Spotify')
    assert 'What would you like' in say(otto, 'increase it to 70')


def test_unrelated_request_invalidates_pending_approval(otto):
    say(otto, 'close discord')
    task = otto.pending.task
    say(otto, 'play Bruno Mars')
    assert task.cancel.is_set()
    assert 'no current question' in say(otto, 'yes')


def test_low_confidence_yes_never_approves(otto):
    say(otto, 'close discord')
    task = otto.pending.task
    assert 'repeat your answer' in otto.handle('yes', heard_conf=-1.2).text
    assert not task.results
    assert 'would close Discord' in say(otto, 'yes')


def test_approval_plan_mutation_rejected(otto):
    say(otto, 'close discord')
    otto.pending.plan.steps[0]['with']['app'] = 'Spotify'
    assert 'changed or expired' in say(otto, 'yes')


def test_approval_revision_change_rejected(otto):
    say(otto, 'close discord')
    otto.pending.task.revision += 1
    assert 'changed or expired' in say(otto, 'yes')


def test_expired_yes_never_executes(otto):
    say(otto, 'close discord')
    task = otto.pending.task
    otto.pending.expires = 0
    assert 'no current question' in say(otto, 'yes')
    assert task.cancel.is_set() and not task.results


def test_simulation_cannot_be_repeated_as_verified_action(otto):
    say(otto, 'play Bruno Mars')
    assert 'no verified action' in say(otto, 'do that again')


def test_c1_spotify_workflow_never_splits_or_googles(otto):
    def no_brain(*args, **kwargs):
        raise AssertionError('Deterministic music workflow should not need the brain')
    otto.brain.ask = no_brain
    reply = say(otto, 'open spotify and search for the hills by the weeknd and play it')
    assert 'would play the hills by the weeknd' in reply
    assert 'Google' not in reply and not otto.queue


def test_spotify_voice_prefix_without_open(otto):
    def no_brain(*args, **kwargs):
        raise AssertionError('Must compile without splitting')
    otto.brain.ask = no_brain
    reply = say(otto, 'Spotify and search for The Hills by The Weekend and Play it.')
    assert reply.count('would play') == 1 and not otto.queue


def test_c1_voice_search_order_keeps_spotify(otto):
    reply = say(otto, 'Can you search on Spotify the shade by Rex Orange County?')
    assert 'Spotify' in reply and 'Google' not in reply and 'would play' not in reply


@pytest.mark.parametrize('utterance', [
    'Open Spotify and search for The Hills by the weekend',
    'Search on Spotify, The Shade by Rex Orange County',
    'No, I want you to search on Spotify the shade by Rex Orange County',
])
def test_c1_reported_voice_search_variants(otto, utterance):
    def no_brain(*args, **kwargs):
        raise AssertionError('Explicit search must not be rewritten by the brain')
    otto.brain.ask = no_brain
    reply = say(otto, utterance)
    assert 'Spotify' in reply and 'would play' not in reply and 'Google' not in reply


def test_new_music_goal_does_not_learn_old_pending_request(otto):
    from core import learning
    say(otto, 'valorant')
    say(otto, 'Search on Spotify, The Shade by Rex Orange County')
    assert not any(row['text'] == 'valorant' for row in learning.load_examples())


def test_c1_unbound_reference_asks(otto):
    assert 'Which song' in say(otto, 'play the first result')


@pytest.mark.parametrize('utterance', ['It was not played.', 'It was not played on Spotify', 'You did not play it'])
def test_failure_feedback_never_rewrites_or_replays(otto, utterance):
    def no_brain(*a, **kw):
        raise AssertionError('Failure feedback must not be rewritten')
    otto.brain.ask = no_brain
    assert 'dry-run' in say(otto, utterance)
    assert not otto.queue


def test_filler_does_not_create_heard_question(otto):
    assert otto.handle('um', heard_conf=-1.06).text == ''
    assert otto.pending is None


def test_explicit_search_bypasses_screen_route(otto):
    first = say(otto, 'can you search what is Otto')
    assert 'Google' in first and 'what is otto' in first
    second = say(otto, 'I want you to look at my screen and search on google chrome')
    assert 'Google' in second and 'what is otto' in second
    assert 'confirm Google Chrome is open' not in second and not otto.queue


def test_c1_quoted_queue_is_a_title(otto):
    assert 'would play Queue' in say(otto, 'play "Queue"')


def test_middle_zone_asks_then_learns(otto):
    from core import learning
    assert say(otto, "valorant") == "Open VALORANT?"
    assert "would open VALORANT" in say(otto, "yeah")
    assert any(r["text"] == "valorant" and r["area"] == "apps" for r in learning.load_examples())


def test_risky_asks_first(otto):
    assert say(otto, "close discord").startswith("Just checking")
    assert "would close Discord" in say(otto, "yes")


def test_recipe_saved_and_replayed(otto, monkeypatch):
    from hands import registry
    from core.tasks import Outcome, OutcomeStatus, Evidence
    # Simulation must not be learned as a successful execution.
    first = otto.handle("search for taylor swift in discord")
    assert 'save that' not in first.text
    assert not otto.last['ok']
    otto.dry_run = False
    state = {}
    def backend(name):
        def run(**args):
            state[name] = dict(args)
            return Outcome(OutcomeStatus.VERIFIED, 'Verified fake app state.', evidence=[
                Evidence('fake_app', expected=dict(args), observed=dict(state[name]))])
        return run
    for name in ('open_app', 'hotkey', 'type_text'):
        monkeypatch.setattr(registry.ACTIONS[name], 'fn', backend(name))
    first = otto.handle("search for taylor swift in discord")
    assert "save that" in first.text
    assert say(otto, "save that").startswith("Saved")
    again = otto.handle("search for taylor swift in discord")
    assert "plan: recipe" in again.details


def test_music_shortcut_and_game(otto):
    assert "would play the hills by the weeknd" in say(otto, 'open spotify, search and play "the hills" by "the weeknd"')
    assert "would open VALORANT" in say(otto, "play valorant")


def test_multi_step(otto):
    r = say(otto, "open discord, then set a timer for 20 minutes")
    assert "would open Discord" in r and "20 minutes timer" in r


def test_followup_rewrite(otto):
    say(otto, "find my resume")
    r = otto.handle("its called student resume")
    assert 'understood as: "find a file called student resume"' in r.details


def test_gibberish(otto):
    assert say(otto, "dadawaddac") == "Sorry, I didn't catch that."


@pytest.mark.parametrize("text", ["Could you play Bruno Mars?", "play run", "play unknown game"])
def test_music_never_fuzzy_launches_an_app(otto, monkeypatch, text):
    monkeypatch.setattr(otto.apps, "apps", otto.apps.apps + [{"name": "Run", "id": "run"}])
    reply = otto.handle(text)
    assert "would play" in reply.text
    assert "would open" not in reply.text


def test_exact_game_alias_still_launches(otto):
    assert "would open VALORANT" in say(otto, "play val")


def test_explicit_music_overrides_game_alias(otto):
    assert "would play" in say(otto, 'play the song "valorant"')


def test_complete_correction_does_not_use_followup_model(otto):
    say(otto, "play in the hills")
    reply = otto.handle("No, can you play The Hills?")
    assert "would play The Hills" in reply.text
    assert "student resume" not in reply.text


@pytest.mark.parametrize("text,expected", [
    ("play The Hills, then set a timer for 20 minutes", True),
    ("open spotify and play The Hills, then set a timer for 20 minutes", True),
    ('play "Then and Now"', False),
    ('play "Come and Go" by Juice WRLD', False),
    ("play 'Then and Now'", False),
    ("open spotify and play The Hills", False),
    ("open spotify and search lofi beats", False),
])
def test_music_compound_detection(otto, text, expected):
    assert otto._is_multi_step(text) is expected


def test_music_and_timer_reach_separate_actions(otto):
    original = otto.brain.ask
    def ask(job, prompt, **kw):
        if "Split it" in prompt:
            return BrainReply("", {"steps": ["play The Hills", "set a timer for 20 minutes"]}, "fake", 0)
        return original(job, prompt, **kw)
    otto.brain.ask = ask
    reply = say(otto, "play The Hills, then set a timer for 20 minutes")
    assert "would play The Hills" in reply and "20 minutes timer" in reply


def test_queue_request_never_starts_playback(otto):
    assert "can't add songs to the queue" in say(otto, "queue up The Hills")
