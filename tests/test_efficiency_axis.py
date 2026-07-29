# -*- coding: utf-8 -*-
"""Engine-free tests for the damage-efficiency bar's domain pieces: the five-stop damage axis
(stops -> equal quarters) and the `>=`-inclusive band index. All pure -- no client, no game.

THR is the same fixture the mark-axis tests use (tests/test_progress_bar_domain.py) and the same
tank the phase-1 tuner ships as its default mock (Obj. 140: 2450/3050/3620/4400), so the numbers
below can be read straight off tools/dev/eff_bar_tuner.html's self-check.
"""
import pytest

from moe_calculator.domain.battle_builder import (
    efficiency_band, efficiency_bar_x, efficiency_stops)

THR = {1: 2450, 2: 3050, 3: 3620, 100: 4400}
STOPS = (0.0, 2450.0, 3050.0, 3620.0, 4400.0)

# NOTE the visual axis itself (domain/constants.EFFICIENCY_BAR_STOPS, which efficiency_bar_x now
# interpolates between) is NOT restated here as its own literal -- that assertion was its own
# right-hand side. It is pinned against the shipped stylesheet's tick rules AND the tuner's meta
# block by tests/test_efficiency_surface_mirror.py, which is the copy that can actually drift.


# --- efficiency_stops ----------------------------------------------------------

def test_stops_are_zero_then_the_four_requirements():
    assert efficiency_stops(THR) == STOPS


def test_stops_are_unusable_without_a_threshold_table():
    assert efficiency_stops({}) is None
    assert efficiency_stops(None) is None


@pytest.mark.parametrize("thresholds", [
    {2: 3050, 3: 3620, 100: 4400},                 # r65 missing
    {1: 2450, 3: 3620, 100: 4400},                 # r85 missing
    {1: 2450, 2: 3050, 100: 4400},                 # r95 missing
    {1: 2450, 2: 3050, 3: 3620},                   # the 100 goalpost missing
])
def test_stops_are_unusable_when_any_requirement_is_missing(thresholds):
    # snap.thresholds is all-or-nothing upstream, so this is belt-and-braces: there is no
    # partial-axis path, a hole degrades the whole axis rather than half-drawing it.
    assert efficiency_stops(thresholds) is None


@pytest.mark.parametrize("thresholds", [
    {1: 0, 2: 3050, 3: 3620, 100: 4400},           # a zero stop
    {1: 2450, 2: 2450, 3: 3620, 100: 4400},        # equal stops -> a zero-width segment
    {1: 2450, 2: 3050, 3: 3000, 100: 4400},        # non-monotone
    {1: -10, 2: 3050, 3: 3620, 100: 4400},         # negative
])
def test_stops_are_unusable_when_not_strictly_ascending(thresholds):
    # A zero-width segment would divide by zero in efficiency_bar_x, so it must never get there.
    assert efficiency_stops(thresholds) is None


def test_stops_fail_soft_on_unreadable_values():
    assert efficiency_stops({1: "x", 2: 3050, 3: 3620, 100: 4400}) is None
    assert efficiency_stops({1: None, 2: 3050, 3: 3620, 100: 4400}) is None
    assert efficiency_stops("not a dict") is None


# --- efficiency_bar_x ----------------------------------------------------------

@pytest.mark.parametrize("damage,expected", [
    (0, 0.0),
    (2450, 25.0),        # exactly on r65  -> the first quarter boundary
    (3050, 50.0),        # exactly on r85
    (3620, 75.0),        # exactly on r95
    (4400, 100.0),       # exactly on the goalpost
])
def test_each_requirement_lands_on_its_own_quarter(damage, expected):
    # THE POINT of the axis, and the reason a separate "unequal segments still get equal quarters"
    # test was redundant: the four DAMAGE gaps here are 2450/600/570/780 wide, yet each lands its
    # own 25 %. A single linear damage->x map would bunch r85/r95 near the tail.
    assert efficiency_bar_x(damage, STOPS) == pytest.approx(expected)


@pytest.mark.parametrize("damage,expected", [
    (1225, 12.5),        # half-way to r65
    (2750, 37.5),        # half-way between r65 and r85
    (3335, 62.5),        # half-way between r85 and r95
    (4010, 87.5),        # half-way between r95 and the goalpost
])
def test_interpolation_inside_a_quarter_is_linear(damage, expected):
    assert efficiency_bar_x(damage, STOPS) == pytest.approx(expected)


def test_bar_x_is_clamped_at_both_ends():
    assert efficiency_bar_x(9999, STOPS) == 100.0     # past the goalpost pins at full
    assert efficiency_bar_x(-500, STOPS) == 0.0       # below zero pins at empty


def test_bar_x_is_monotonically_increasing():
    prev = -1.0
    for damage in range(0, 5000, 25):
        x = efficiency_bar_x(damage, STOPS)
        assert x >= prev
        prev = x


def test_bar_x_fails_soft_on_an_unusable_axis():
    assert efficiency_bar_x(1900, None) == 0.0


@pytest.mark.parametrize("bad", [None, float("nan")])
def test_bar_x_fails_soft_on_unreadable_damage(bad):
    assert efficiency_bar_x(bad, STOPS) == 0.0


# --- efficiency_band -----------------------------------------------------------

@pytest.mark.parametrize("damage,expected", [
    (0, 0),
    (1900, 0),
    (2449, 0),
    (2450, 1),       # THE EDGE: damage exactly on r65 is ALREADY band 1 (green), `>=` inclusive
    (3049, 1),
    (3050, 2),       # exactly on r85 -> teal
    (3619, 2),
    (3620, 3),       # exactly on r95 -> violet
    (4399, 3),
    (4400, 4),       # exactly on the goalpost -> gold
    (9999, 4),
])
def test_band_is_the_highest_requirement_passed_inclusive(damage, expected):
    assert efficiency_band(damage, STOPS) == expected


def test_band_indexes_the_same_stop_the_axis_does():
    # The band index must be the stop's own index, expressed DERIVATIVELY (STOPS[i] -> i) rather
    # than as the literal pairs above, so a re-tune of THR propagates. The matching
    # efficiency_bar_x(STOPS[i]) == EFFICIENCY_BAR_STOPS[i] half is gone: it restated
    # test_each_requirement_lands_on_its_own_quarter with the constant substituted for its
    # literals, and the constant itself is pinned to the stylesheet in
    # tests/test_efficiency_surface_mirror.py.
    for i in (1, 2, 3, 4):
        assert efficiency_band(STOPS[i], STOPS) == i


def test_band_is_zero_on_an_unusable_axis():
    assert efficiency_band(9999, None) == 0


@pytest.mark.parametrize("bad", [None, float("nan")])
def test_band_fails_soft_on_unreadable_damage(bad):
    assert efficiency_band(bad, STOPS) == 0
