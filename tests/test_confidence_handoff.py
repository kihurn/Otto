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


