"""No desktop effects: assert validation blocks complete plans before execution."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from core import planner, safety
from core.tasks import Evidence, Outcome, OutcomeStatus, Task
from hands import registry


@pytest.fixture(autouse=True)
def registered_actions():
    registry.load_all()


def step(name="open_app", **args):
    return {"do": name, "with": args}


@pytest.mark.parametrize("bad", [
    None, {}, "open_app", [], [None],
    [step("invented")],
    [step("open_app")],
    [step("open_app", app="Spotify", extra="ignored?")],
    [step("open_app", app=[])],
    [step("open_app", app="")],
    [step("open_app", app="{app}")],
    [step("open_path", path={"$ref": "find.selected_path"})],
    [step("set_volume", level=True)],
    [step("set_volume", level="40")],
    [step("set_volume", level=101)],
    [step("set_volume", level=10 ** 1000)],
    [step("wait", seconds=float("nan"))],
    [step("wait", seconds=float("inf"))],
    [step("wait", seconds=6)],
    [step("set_timer", seconds=-1)],
    [step("set_alarm", at="24:00")],
    [step("play_music", query="The Hills", kind="video")],
    [step("media_key", key="delete")],
    [{"do": "open_app", "with": {"app": "Spotify"}, "risk": "read"}],
    [{"do": "open_app", "with": []}],
    [{"id": "same", **step("now_playing")}, {"id": "same", **step("now_playing")}],
    [{"id": [], **step("now_playing")}],
    [step("now_playing")] * 9,
])
def test_bad_plans_have_no_effects(monkeypatch, bad):
    calls = []
    def opened(app):
        calls.append(app)
        return registry.Result(True, "opened")
    monkeypatch.setitem(registry.ACTIONS, "open_app", replace(registry.ACTIONS["open_app"], fn=opened))
    # Even a valid first action cannot run when a later step is invalid.
    steps = [step(app="Spotify"), *bad] if isinstance(bad, list) and bad else bad
    result = safety.run_plan(steps, confirmed=True)
    assert not result.ok and result.data["error_code"] == "invalid_plan"
    assert calls == []


def test_validated_plan_is_a_snapshot():
    original = [step(app="Spotify")]
    validated = planner.validate_steps(original)
    original[0]["with"]["app"] = "Run"
    assert validated[0]["with"]["app"] == "Spotify"


@pytest.mark.parametrize("payload", [
    {"steps": [step(app="Spotify")] * 9},
    {"steps": [step(app="Spotify", unknown="drop me")]},
    {"steps": [step("close_app", app="Discord")]},
    {"steps": [step(app="Spotify")], "version": True},
    {"steps": [step(app="Spotify")], "approved": True},
    {"steps": "open spotify"},
])
def test_model_plan_rejected_without_truncating_or_filtering(payload):
    brain = SimpleNamespace(ask=lambda *a, **k: SimpleNamespace(data=payload, model="fake"))
    plan = planner.brain_plan("open Spotify", None, brain)
    assert plan.error and plan.steps == []


def test_model_plan_accepts_versioned_steps():
    payload = {"version": 1, "steps": [{"id": "launch", **step(app="Spotify")}]}
    brain = SimpleNamespace(ask=lambda *a, **k: SimpleNamespace(data=payload, model="fake"))
    plan = planner.brain_plan("open Spotify", None, brain)
    assert not plan.error and plan.steps == payload["steps"]


def test_builtin_only_actions_allowed_for_legacy_plans():
    assert planner.validate_steps([step("close_app", app="Discord")])
    with pytest.raises(registry.InvalidPlan):
        planner.validate_steps([step("close_app", app="Discord")], for_brain=True)


def test_legacy_acceptance_is_never_verified():
    result = registry.Result(True, "submitted", {"app": "Spotify"})
    outcome = result.to_outcome()
    assert outcome.status == OutcomeStatus.DISPATCHED and not outcome.ok
    assert outcome.side_effect_possible
    assert result.to_outcome(dry_run=True).status == OutcomeStatus.SIMULATED
    assert not result.to_outcome(dry_run=True).side_effect_possible
    assert registry.Result(False, "failed").to_outcome().status == OutcomeStatus.FAILED
    assert registry.Result(False, "invalid dry run").to_outcome(dry_run=True).status == OutcomeStatus.FAILED


def test_verified_requires_evidence_and_only_verified_is_ok():
    with pytest.raises(ValueError):
        Outcome(OutcomeStatus.VERIFIED, "Playing")
    outcome = Outcome(OutcomeStatus.VERIFIED, "Playing", evidence=[Evidence("fake_player")])
    assert outcome.ok
    for status in OutcomeStatus:
        if status != OutcomeStatus.VERIFIED:
            assert not Outcome(status, "test").ok


def test_task_state_not_shared_between_requests():
    first, second = Task("first", []), Task("second", [])
    first.cancel.set()
    first.results["test"] = Outcome(OutcomeStatus.CANCELLED, "cancelled")
    assert first.id != second.id and not second.cancel.is_set() and not second.results
    with pytest.raises(ValueError):
        Task("bad mode", [], mode="training_live")
