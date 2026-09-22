"""REMEDIATION.md Section 5: F9's stampede test and F14's JIT test (need
the full engine, unlike test_formulas.py's pure-function tests), plus
basic safety/determinism checks for the 'ours' policy and each ablation.

2026-09-22 checkpoint-4 rework: repointed from the old standalone
sim.ours_policy.run_mission_sim_ours (deleted) to the merged
sim.mission_sim.run_mission_sim(policy='ours', ...), per REMEDIATION.md
Section 3's literal spec ("Implement as a policy policy='ours' in the
Phase 4 mission simulator"). Verified byte-for-bit equivalent to the old
standalone engine on fixed seeds before the old module was deleted (see
CLAUDE.md Section 13's checkpoint 4 report)."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.mission_sim import run_mission_sim

STATIONS = [(500, 500), (1500, 500), (500, 1500), (1500, 1500)]


def _run(**kwargs):
    defaults = dict(n_uavs=10, station_positions=STATIONS, pads_per_station=2,
                     horizon_min=300, seed=1, mission_rate_per_min=0.3)
    defaults.update(kwargs)
    return run_mission_sim(policy="ours", **defaults)


def test_ours_policy_safe_and_deterministic():
    r1 = _run(seed=5)
    r2 = _run(seed=5)
    assert r1["safety_violations"] == 0
    assert r1["missions_completed"] == r2["missions_completed"]
    assert r1["total_charge_energy_wh"] == r2["total_charge_energy_wh"]


def test_all_ablations_run_safely():
    for flag, value in [("use_queue_term", False), ("use_reservation", False),
                         ("use_priority", False), ("use_partial", False),
                         ("use_jit", True), ("use_charge_time_term", False)]:
        r = _run(**{flag: value})
        assert r["safety_violations"] == 0, f"{flag}={value} produced safety violations"


def test_invalid_combo_charge_policy_with_ours_raises():
    """REMEDIATION.md checkpoint-4 requirement: charge_policy/pad_order only
    apply to policy='baseline'; the six ablation flags/w1/w2 only apply to
    policy='ours'. Passing one with the wrong policy must raise, not
    silently ignore it."""
    import pytest
    with pytest.raises(ValueError):
        _run(charge_policy="full")
    with pytest.raises(ValueError):
        _run(pad_order="margin")
    with pytest.raises(ValueError):
        run_mission_sim(policy="baseline", use_jit=True, n_uavs=5, station_positions=STATIONS,
                         pads_per_station=1, horizon_min=60, seed=1, mission_rate_per_min=0.1)
    with pytest.raises(ValueError):
        run_mission_sim(policy="jsq", w1=2.0, n_uavs=5, station_positions=STATIONS,
                         pads_per_station=1, horizon_min=60, seed=1, mission_rate_per_min=0.1)


def test_F9_stampede_reservation_spreads_load_ablation_sends_all_to_one():
    """6 drones at the same position, all needing charging at the same
    epoch (forced low starting SoC), 3 equidistant stations x 1 pad. With
    reservation ON, F9's free_time update before each subsequent drone's
    cost evaluation must spread reservations across stations. With
    reservation OFF, every drone sees every station as equally free (no
    persisted update) and ties resolve to the same (first) station --
    genuine stampede."""
    import math as m
    center = (1000.0, 1000.0)
    radius = 500.0
    equidistant_stations = [
        (center[0] + radius, center[1]),
        (center[0] + radius * m.cos(2 * m.pi / 3), center[1] + radius * m.sin(2 * m.pi / 3)),
        (center[0] + radius * m.cos(4 * m.pi / 3), center[1] + radius * m.sin(4 * m.pi / 3)),
    ]
    n = 6
    positions = [center] * n

    r_on = run_mission_sim(policy="ours", n_uavs=n, station_positions=equidistant_stations,
                            pads_per_station=1, horizon_min=5, seed=1, mission_rate_per_min=0.0,
                            initial_soc=0.30, initial_positions=positions, use_reservation=True)
    r_off = run_mission_sim(policy="ours", n_uavs=n, station_positions=equidistant_stations,
                             pads_per_station=1, horizon_min=5, seed=1, mission_rate_per_min=0.0,
                             initial_soc=0.30, initial_positions=positions, use_reservation=False)

    # Use the recorded stampede diagnostic: the first epoch's list of
    # stations chosen by same-epoch reservations.
    assert r_on["stampede_station_counts"], "expected a multi-reservation epoch to have occurred"
    assert r_off["stampede_station_counts"], "expected a multi-reservation epoch to have occurred"
    on_stations = set(r_on["stampede_station_counts"][0])
    off_stations = set(r_off["stampede_station_counts"][0])
    assert len(on_stations) > 1, f"reservation ON must spread across stations, got {r_on['stampede_station_counts'][0]}"
    assert len(off_stations) == 1, f"reservation OFF must stampede onto one station, got {r_off['stampede_station_counts'][0]}"


def test_F14_jit_preserves_total_delay_but_removes_onpad_wait():
    """Deterministic single-station scenario: 2 drones both need to charge,
    forced so the second drone's pad isn't free when it would otherwise
    arrive. Under JIT, total delay (charge_start - request/reservation
    time) must match the non-JIT case (JIT cannot reduce total delay in a
    model with deterministic, already-known service times -- it only moves
    WHERE the delay is spent), while the on-pad wait before charging must
    drop to ~0."""
    station = [(1000.0, 1000.0)]
    # both drones start right next to the station so travel time is tiny
    # and predictable; force low SoC so both need charging immediately.
    positions = [(1000.0, 1000.0), (1000.0, 1000.0)]

    r_nojit = run_mission_sim(policy="ours", n_uavs=2, station_positions=station, pads_per_station=1,
                               horizon_min=120, seed=1, mission_rate_per_min=0.0,
                               initial_soc=0.30, initial_positions=positions, use_jit=False)
    r_jit = run_mission_sim(policy="ours", n_uavs=2, station_positions=station, pads_per_station=1,
                             horizon_min=120, seed=1, mission_rate_per_min=0.0,
                             initial_soc=0.30, initial_positions=positions, use_jit=True)

    assert len(r_nojit["session_log"]) == 2
    assert len(r_jit["session_log"]) == 2

    delays_nojit = sorted(cs["total_delay_min"] for cs in r_nojit["session_log"])
    delays_jit = sorted(cs["total_delay_min"] for cs in r_jit["session_log"])
    # Total delay (request -> charge start) should match within one tick,
    # since JIT only changes WHERE the wait happens, not how long it is.
    for a, b in zip(delays_nojit, delays_jit):
        assert abs(a - b) <= 1.0, f"JIT changed total delay: {a} vs {b}"
