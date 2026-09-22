import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.energy import charge_power_w, flight_energy_wh, soc_after_charging, time_to_reach_target_min


def test_flight_energy_scales_with_distance():
    assert flight_energy_wh(100) == 1.0
    assert flight_energy_wh(0) == 0.0


def test_charge_power_bands():
    assert charge_power_w(0.5) == 200.0
    assert charge_power_w(0.8) == 120.0
    assert charge_power_w(0.95) == 50.0


def test_soc_after_charging_monotonic_and_bounded():
    s = soc_after_charging(0.3, minutes=10, battery_wh=90)
    assert 0.3 < s <= 1.0
    s_more = soc_after_charging(0.3, minutes=100, battery_wh=90)
    assert s_more == 1.0  # fully charged, clamped


def test_soc_after_charging_zero_minutes_is_noop():
    assert soc_after_charging(0.5, minutes=0, battery_wh=90) == 0.5


def test_charging_to_100_is_not_time_optimal():
    """The whole point of the CC-CV curve: the last 10% (90-100%) takes
    disproportionately long relative to the energy it delivers."""
    battery_wh = 90
    t_0_to_70 = time_to_reach_target_min(0.0, 0.70, battery_wh)
    t_70_to_90 = time_to_reach_target_min(0.70, 0.90, battery_wh)
    t_90_to_100 = time_to_reach_target_min(0.90, 1.00, battery_wh)

    # same 10% of capacity, much slower at the top (50W vs 200W trickle)
    energy_per_10pct = 0.10 * battery_wh
    rate_low = energy_per_10pct / (t_90_to_100 / 60.0)  # should be ~50W
    assert abs(rate_low - 50.0) < 1e-6
    assert t_90_to_100 > t_0_to_70 / 7  # last 10% alone is disproportionately slow
    assert t_0_to_70 + t_70_to_90 + t_90_to_100 == time_to_reach_target_min(0.0, 1.0, battery_wh)


def test_time_to_reach_target_roundtrip_with_soc_after_charging():
    battery_wh = 90
    soc_start, soc_target = 0.3, 0.85
    t = time_to_reach_target_min(soc_start, soc_target, battery_wh)
    s_final = soc_after_charging(soc_start, t, battery_wh)
    assert abs(s_final - soc_target) < 1e-6
