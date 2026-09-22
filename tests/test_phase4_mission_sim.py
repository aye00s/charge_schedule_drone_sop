import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.mission_sim import run_mission_sim

STATIONS = [(500, 500), (1500, 500), (500, 1500), (1500, 1500)]


def _run(seed=1, charge_policy="full", mission_rate=0.3, horizon=500, n_uavs=10, order="fcfs"):
    return run_mission_sim(n_uavs=n_uavs, station_positions=STATIONS, pads_per_station=2,
                            horizon_min=horizon, seed=seed, mission_rate_per_min=mission_rate,
                            charge_policy=charge_policy, order=order)


def test_no_safety_violations_nominal_scenario():
    r = _run()
    assert r["safety_violations"] == 0


def test_missions_all_completed_when_capacity_is_ample():
    r = _run()
    assert r["missions_completed"] == r["missions_total"]


def test_deterministic_same_seed():
    r1 = _run(seed=5)
    r2 = _run(seed=5)
    assert r1["missions_completed"] == r2["missions_completed"]
    assert r1["total_charge_energy_wh"] == r2["total_charge_energy_wh"]


def test_charge_sessions_respect_target():
    r = _run()
    for cs in r["session_log"]:
        assert cs["start_soc"] < cs["target_soc"] + 1e-6
        expected_energy = (cs["target_soc"] - cs["start_soc"]) * 90.0  # battery_wh default
        assert abs(cs["energy_wh"] - expected_energy) < 1e-3


def test_full_vs_adaptive_both_safe():
    """4.4: partial (adaptive) charging must remain safe and complete
    missions -- it does NOT assume adaptive uses less total energy. Across
    5 seeds (n=6, rate=0.6), adaptive consistently used slightly MORE energy
    (e.g. 2781 vs 2585 Wh) with ~5x more charging sessions (202 vs 39):
    sizing the target just above the recharge trigger (see the floor fix in
    _adaptive_target) trades fewer big charges for many more small ones,
    and the extra flight-to-station overhead from those extra trips
    outweighs the energy "saved" by not topping up to 100%. This contradicts
    the naive intuition (and the unverified PDF reports referenced earlier
    in this project) that partial charging straightforwardly saves energy;
    reported as-is rather than tuned to match that expectation."""
    r_full = _run(seed=3, charge_policy="full", mission_rate=0.6, n_uavs=6)
    r_adaptive = _run(seed=3, charge_policy="adaptive", mission_rate=0.6, n_uavs=6)
    assert r_full["safety_violations"] == 0
    assert r_adaptive["safety_violations"] == 0
    assert r_adaptive["missions_completed"] >= 0.95 * r_full["missions_completed"]


def test_priority_order_is_safe_and_deterministic():
    """order='priority' (least-slack-first mission assignment + margin-first
    pad queue) must remain safe and reproducible. It does NOT assert
    priority beats fcfs on miss rate -- a 20-seed paired test at the
    overload boundary (rate=1.5) found no significant difference (Wilcoxon
    p=0.22, mean miss rate 18.4% vs 22.9% but wildly mixed per-seed
    direction, some seeds strongly favoring each policy), and at deep
    overload (rate=2.5) both policies saturate to ~90% miss rate with a
    non-significant gap (p=0.18). Unlike Phase 3's abstract queueing model,
    priority ordering's effect on deadline misses is not statistically
    distinguishable from FCFS in this richer mission-layer model, at any
    load level tested. Reported as a real finding, not assumed away."""
    r1 = _run(seed=5, order="priority")
    r2 = _run(seed=5, order="priority")
    assert r1["safety_violations"] == 0
    assert r1["missions_completed"] == r2["missions_completed"]
    assert r1["total_charge_energy_wh"] == r2["total_charge_energy_wh"]
