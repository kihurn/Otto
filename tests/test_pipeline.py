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












def test_new_music_goal_does_not_learn_old_pending_request(otto):
    from core import learning
    say(otto, 'valorant')
    say(otto, 'Search on Spotify, The Shade by Rex Orange County')
    assert not any(row['text'] == 'valorant' for row in learning.load_examples())






def test_filler_does_not_create_heard_question(otto):
    assert otto.handle('um', heard_conf=-1.06).text == ''
    assert otto.pending is None




def test_c1_quoted_queue_is_a_title(otto):
    assert 'would play Queue' in say(otto, 'play "Queue"')




def test_risky_asks_first(otto):
    assert say(otto, "close discord").startswith("Just checking")
    assert "would close Discord" in say(otto, "yes")










def test_gibberish(otto):
    assert say(otto, "dadawaddac") == "Sorry, I didn't catch that."






def test_explicit_music_overrides_game_alias(otto):
    assert "would play" in say(otto, 'play the song "valorant"')








