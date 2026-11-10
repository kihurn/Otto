"""The rules that turn a sentence into an action. Add a line here whenever you fix a phrasing."""

import pytest

from core import answers, details, guards
from hands import apps

CASES = [
    ("apps", "can you open spotify?", "apps.open", {"app": "Spotify"}),
    ("apps", "open spotify and search lofi beats", "apps.search_in_app", {"app": "spotify", "query": "lofi beats"}),
    ("apps", "search for drake on spotify", "apps.search_in_app", {"query": "drake"}),
    ("apps", "close valorant", "apps.close", {"app": "VALORANT"}),
    ("apps", "switch to discord", "apps.switch_to", {"app": "Discord"}),
    ("apps", "open vs code", "apps.open", {"app": "Visual Studio Code"}),
    ("apps", "open obs", "apps.open", {"app": "OBS Studio"}),
    ("apps", "close chrome pls", "apps.close", {"app": "Google Chrome"}),
    ("apps", 'can you help me open spotify, search and play "the hills" by "the weeknd"', "media.play_music",
     {"query": "the hills", "artist": "the weeknd", "kind": "track"}),
    ("media", "play my music on spotify", "media.play_liked", {}),
    ("media", "play the hills", "media.play_music", {"query": "the hills"}),
    ("media", "play the album after hours", "media.play_music", {"query": "after hours", "kind": "album"}),
    ("media", "play my playlist gym", "media.play_music", {"query": "gym", "kind": "playlist"}),
    ("media", "play music", "media.play", {}),
    ("media", "pause", "media.pause", {}),
    ("media", "volume 40", "media.set_volume", {"level": 40}),
    ("media", "its too loud", "media.volume_down", {}),
    ("media", "skip", "media.next", {}),
    ("question", "whats playing", "media.now_playing", {}),
    ("web", "google how to make pasta", "web.web_search", {"query": "how to make pasta"}),
    ("web", "search up best gaming mouse", "web.web_search", {"query": "best gaming mouse"}),
    ("web", "take me to github", "web.open_site", {"site": "github"}),
    ("files", "find my biology notes", "files.find", {"query": "biology notes"}),
    ("files", "find a file called student resume", "files.find", {"query": "student resume"}),
    ("files", "find the pdf for my assignment", "files.find", {"query": "assignment ext:pdf"}),
    ("notes", "write down call the bank tomorrow", "notes.new_note", {"text": "call the bank tomorrow"}),
    ("notes", "write a quick todo list", "notes.new_note", {"title": "todo list"}),
    ("timer", "remind me in 15 minutes to check the food", "timer.set_timer", {"seconds": 900.0, "label": "check the food"}),
    ("timer", "set a timer for an hour and a half", "timer.set_timer", {"seconds": 5400.0}),
    ("timer", "stop my timer", "timer.cancel", {}),
]


@pytest.mark.parametrize("area,text,expected,params", CASES)
def test_rules(area, text, expected, params):
    i = details.by_rules(area, text, apps.INDEX)
    assert i is not None, f"no rule matched {text!r}"
    assert f"{i.area}.{i.action}" == expected
    for k, v in params.items():
        assert i.params.get(k) == v, f"{k}: {i.params.get(k)!r} != {v!r}"


def test_near_miss_app_asks():
    i = details.by_rules("apps", "open valor and", apps.INDEX)
    assert i.params["app"] == "VALORANT" and i.check_app == "VALORANT"


@pytest.mark.parametrize("text,kind", [("yes", "yes"), ("yeah do it", "yes"), ("nah", "no"),
                                        ("no wait open discord", None), ("Lo-fi beats", None)])
def test_reply_kind(text, kind):
    assert guards.reply_kind(text) == kind


@pytest.mark.parametrize("text,cmd", [("save that", "save"), ("yeah save that", "save"), ("forget that one", "forget"),
                                       ("remember that for me", None)])
def test_memory_command(text, cmd):
    assert guards.memory_command(text) == cmd


def test_gibberish():
    assert guards.is_gibberish("dadawaddac")
    assert not guards.is_gibberish("dad awdafd open spotify")


@pytest.mark.parametrize("text,rest", [("Hey Otto, open Spotify.", "open Spotify"), ("Hey Otto.", ""),
                                        ("auto save my file", None), ("I was talking about Otto yesterday", None)])
def test_wake(text, rest):
    words = ["hey otto", "hi otto", "ok otto", "okay otto", "yo otto", "hey auto", "hey otter", "otto"]
    assert guards.wake_rest(text, words) == rest


@pytest.mark.parametrize("text,answer", [("what's 15 percent of 80", "That's 12."), ("whats 20 times 15", "That's 300."),
                                          ("what's the square root of 144", "That's 12.")])
def test_maths(text, answer):
    assert answers.local_answer(text) == answer
