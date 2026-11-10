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


def test_middle_zone_asks_then_learns(otto):
    from core import learning
    assert say(otto, "valorant") == "Open VALORANT?"
    assert "would open VALORANT" in say(otto, "yeah")
    assert any(r["text"] == "valorant" and r["area"] == "apps" for r in learning.load_examples())


def test_risky_asks_first(otto):
    assert say(otto, "close discord").startswith("Just checking")
    assert "would close Discord" in say(otto, "yes")


def test_recipe_saved_and_replayed(otto):
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
