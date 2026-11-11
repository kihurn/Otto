"""A user-configured acting floor also applies to saved calibration and split requests."""
import pytest
from core.router import serving_bars
from core.pipeline import Reply
from test_pipeline import otto  # noqa: F401


@pytest.mark.parametrize('measured,enabled,expected', [
    ({'act_bar': .7}, True, .9), ({'act_bar': .95}, True, .95),
    (None, True, .9), ({'act_bar': .7}, False, .9),
])
def test_acting_floor_is_always_applied(measured, enabled, expected):
    zones = {'act_bar': .85, 'act_bar_floor': .9, 'use_measured': enabled}
    assert serving_bars(zones, measured)[0] == expected


@pytest.mark.parametrize('confidence,split,use_qwen', [
    (.899, False, True), (.899, True, True), (.9, False, False), (.95, False, False),
])
def test_below_ninety_goes_to_qwen_including_split_requests(otto, monkeypatch, confidence, split, use_qwen):
    otto.settings['zones'].update(act_bar=.9, act_bar_floor=.9)
    otto.router.meta = {'bars': {'act_bar': .7}}
    monkeypatch.setattr(otto.router, 'predict', lambda t: {
        'area': 'apps', 'prob': confidence, 'ms': 1, 'top': []})
    calls = []
    monkeypatch.setattr(otto, '_qwen', lambda t: calls.append(t) or Reply('Qwen handled this.'))
    otto._process('open discord', from_split=split)
    assert bool(calls) is use_qwen
