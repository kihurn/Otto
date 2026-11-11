"""Regression tests for the 1.2 review findings (docs/V1_2_FINAL_REVIEW.md, R1–R6)."""

import random

from core.router import measure_bars, precision_at


# ---- R3: confidence ties ---------------------------------------------------------------------

def test_r3_tied_group_with_mistakes_is_not_accepted():
    preds = [{"prob": .9, "right": i < 8} for i in range(10)]   # 80% right, all at the same confidence
    bars = measure_bars(preds)
    assert bars["act_bar"] is None


def test_r3_bar_precision_holds_and_ignores_row_order():
    preds = ([{"prob": .99, "right": True}] * 20 + [{"prob": .9, "right": True}] * 5 +
             [{"prob": .9, "right": False}] * 3 + [{"prob": .5, "right": False}] * 4)
    for seed in range(5):
        rows = preds[:]
        random.Random(seed).shuffle(rows)
        bar = measure_bars(rows)["act_bar"]
        assert bar == .99
        n, precision = precision_at(rows, bar)
        assert n == 20 and precision >= .95


def test_r3_bar_is_exact_not_rounded():
    preds = [{"prob": 0.98765, "right": True}] * 10 + [{"prob": 0.9874, "right": False}] * 5
    bar = measure_bars(preds)["act_bar"]
    assert bar == 0.98765
    assert precision_at(preds, bar) == (10, 1.0)


def test_r3_no_bar_when_nothing_qualifies():
    assert measure_bars([{"prob": .9, "right": False}] * 12)["act_bar"] is None


# ---- R2: candidates are judged at the bar they will really use --------------------------------

def _scores(preds):
    from core.router import measure_bars
    return {"accuracy": sum(p["right"] for p in preds) / len(preds), "preds": preds, "bars": measure_bars(preds)}


def test_r2_candidate_with_lower_serving_bar_is_rejected():
    from core import training
    from core.router import serving_bars
    preds = [{"text": str(i), "gold": "media", "right": i < 38, "prob": .99 if i < 38 else .72} for i in range(40)]
    s = _scores(preds)
    zones = {"act_bar": .85, "use_measured": True, "act_bar_floor": .70}
    candidate_bar = serving_bars(zones, s["bars"])[0]
    assert candidate_bar < .85                                   # the candidate would act more boldly...
    ok, why = training.gate(s, s, .85, candidate_bar)
    assert not ok and "precision" in why                         # ...where it is only 95%, worse than 100%


def test_r2_same_bar_still_passes():
    from core import training
    preds = [{"text": str(i), "gold": "apps", "right": True, "prob": .99} for i in range(20)]
    assert training.gate(_scores(preds), _scores(preds), .85, .85)[0]


def test_r2_promotion_refuses_candidates_approved_by_the_old_check(tmp_path, monkeypatch):
    import pytest
    from types import SimpleNamespace
    from core import config, router, training
    current = tmp_path / "current"
    monkeypatch.setattr(router, "CURRENT", current)
    current.mkdir()
    config.save_json(current / router.META, {"hash": "x"})
    identity = "b" * 32
    cand = tmp_path / "candidates" / identity
    cand.mkdir(parents=True)
    config.save_json(cand / router.META, {"hash": "y"})
    monkeypatch.setattr(training, "dataset", lambda: ([], []))
    config.save_json(cand / "report.json", {"state": "complete", "eligible": True})   # no gate_version
    with pytest.raises(ValueError, match="older check"):
        training.promote(SimpleNamespace(settings={}), identity)


# ---- R1: page content that impersonates Chrome's controls is never clicked or typed into -------

def _ctrl(name, kind, parent=None):
    from types import SimpleNamespace as NS
    return NS(element_info=NS(name=name, control_type=kind), parent=lambda: parent)


def test_r1_page_button_named_new_tab_is_rejected():
    from hands.window_control import chrome_control_ok
    page = _ctrl("Some site", "Document", parent=_ctrl("Chrome", "Pane"))
    assert not chrome_control_ok(_ctrl("New tab", "Button", parent=page))
    assert not chrome_control_ok(_ctrl("Address and search bar", "Edit", parent=page))
    assert not chrome_control_ok(_ctrl("Search Google or type a URL", "Edit", parent=_ctrl("Chrome", "Pane")))


def test_r1_real_toolbar_controls_are_allowed():
    from hands.window_control import chrome_control_ok
    toolbar = _ctrl("", "ToolBar", parent=_ctrl("Chrome", "Pane"))
    assert chrome_control_ok(_ctrl("Address and search bar", "Edit", parent=toolbar))
    assert chrome_control_ok(_ctrl("New tab", "Button", parent=toolbar))
    assert not chrome_control_ok(_ctrl("New tab", "Edit", parent=toolbar))       # wrong control type


def test_r1_click_on_impersonating_page_button_sends_no_click(monkeypatch):
    import sys
    import pytest
    from types import SimpleNamespace as NS
    from hands.window_control import WindowProvider
    clicks = []
    page_button = _ctrl("New tab", "Button", parent=_ctrl("page", "Document"))
    monkeypatch.setitem(sys.modules, "pywinauto", NS(mouse=NS(click=lambda **kw: clicks.append(kw)),
                                                    Desktop=lambda **kw: NS(from_point=lambda *a: page_button)))
    monkeypatch.setitem(sys.modules, "win32gui", NS(WindowFromPoint=lambda p: 1, GetAncestor=lambda *a: 1))
    p = WindowProvider.__new__(WindowProvider)
    p.hwnd = 1
    p.identity = lambda: (123, 1, (0, 0, 100, 100))
    with pytest.raises(ValueError, match="outside the allowed"):
        p.act("click", {"x": .5, "y": .5}, {"identity": p.identity()}, {"app": "Chrome", "query": "Otto", "artist": ""})
    assert clicks == []


# ---- R4: only the exact requested recording counts as success ---------------------------------

import pytest


@pytest.mark.parametrize("playing,query,same", [
    ("The Hills", "The Hills", True),
    ("The Hills - Live", "The Hills", False),
    ("The Hills (Live)", "The Hills", False),
    ("The Hills (Remix)", "The Hills", False),
    ("The Hills - Sped Up", "The Hills", False),
    ("Hills", "The Hills", False),
    ("The Hills Are Alive", "The Hills", False),
    ("Starboy (feat. Daft Punk)", "Starboy", True),
    ("Blinding Lights - Remastered 2021", "Blinding Lights", True),
    ("The Hills (Live)", "The Hills Live", True),
])
def test_r4_same_recording(playing, query, same):
    from hands.spotify_desktop import same_recording
    assert same_recording(playing, query) is same


def test_r4_live_version_is_not_reported_as_success(monkeypatch):
    import sys
    import time
    from types import SimpleNamespace as NS
    from core.tasks import OutcomeStatus, Step, Task
    from hands import apps, media, spotify_desktop, win
    from hands.registry import Result
    monkeypatch.setattr(apps, "open_app", lambda *a: Result(True, "opened"))
    monkeypatch.setattr(apps, "search_in_app", lambda *a: Result(True, "searched"))
    monkeypatch.setattr(win, "find_window", lambda *a: {"hwnd": 1})
    monkeypatch.setattr(win, "foreground", lambda: 1)
    monkeypatch.setitem(sys.modules, "pywinauto", NS(Application=lambda **kw: NS(connect=lambda **kw: NS(window=lambda **kw: object()))))
    monkeypatch.setattr(spotify_desktop, "play_candidates", lambda *a: [NS(invoke=lambda: None)])
    for title, expected in (("The Hills Live", OutcomeStatus.NEEDS_INPUT), ("The Hills", OutcomeStatus.VERIFIED)):
        monkeypatch.setattr(media, "sessions", lambda t=title: [{"app": "Spotify", "status": media.PLAYING,
                                                                 "title": t, "artist": "The Weeknd"}])
        step = Step("s", "play_music", {"query": "The Hills", "artist": "The Weeknd"})
        res = spotify_desktop.play(step, Task("play", [step]), time.monotonic() + 45, lambda text: None)
        assert res.status == expected, (title, res.say)


# ---- R5: one expired audio session doesn't stop the others being restored ---------------------

class _Vol:
    def __init__(self, level=.8):
        self.level, self.dead, self.muted = level, False, False

    def GetMasterVolume(self):
        if self.dead:
            raise OSError("session expired")
        return self.level

    def SetMasterVolume(self, v, ctx):
        if self.dead:
            raise OSError("session expired")
        self.level = v

    def GetMute(self):
        if self.dead:
            raise OSError("session expired")
        return self.muted


def _caps(tmp_path, sessions):
    from types import SimpleNamespace as NS
    from core.audio_focus import SessionCaps
    provider = NS(snapshot=lambda: ("speaker", {k: ("speaker", v) for k, v in sessions.items()}))
    return SessionCaps(provider, .2, tmp_path / "journal.json")


def test_r5_expired_session_does_not_block_restoring_others(tmp_path):
    first, second = _Vol(), _Vol()
    caps = _caps(tmp_path, {"first": first, "second": second})
    caps.update(True)
    assert first.level == second.level == .2
    first.dead = True
    caps.update(False)
    assert second.level == .8                 # the healthy app got its volume back
    assert "first" in caps.owned              # the expired one keeps its receipt for later
    first.dead = False
    caps.update(False)
    assert first.level == .8 and not caps.owned


def test_r5_session_dying_while_capping_is_skipped(tmp_path):
    first, second = _Vol(), _Vol()
    first.dead = True
    caps = _caps(tmp_path, {"first": first, "second": second})
    caps.update(True)
    assert second.level == .2 and "first" not in caps.owned


def test_r5_journal_failure_still_prevents_unrecorded_change(tmp_path):
    import pytest
    vol = _Vol()
    caps = _caps(tmp_path, {"a": vol})

    def broken():
        raise PermissionError("disk full")
    caps.save = broken
    with pytest.raises(PermissionError):
        caps.update(True)
    assert vol.level == .8                    # never changed without a saved receipt


# ---- R6: "save that" after tasks that have no single intent ----------------------------------

@pytest.mark.parametrize("text", ["Use Qwen to search Otto", "open discord, then set a timer",
                                  "switch audio to headphones"])
def test_r6_save_that_without_intent_explains_instead_of_crashing(text):
    from core.pipeline import Otto
    o = Otto.__new__(Otto)
    o.trace = {}
    o.last = {"text": text, "intent": None, "ok": True, "plan": None}
    reply = o._memory("save")
    assert "can't save" in reply.text.lower() or "cannot save" in reply.text.lower()
