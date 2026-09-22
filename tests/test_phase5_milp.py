import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.milp import (solve_charge_schedule_heuristic, solve_charge_schedule_milp,
                       solve_charge_schedule_milp_ccv)


def test_hand_checkable_instance_matches_manual_calculation():
    """Section 8's exact hand-checkable instance: 4 drones, 2 stations x 1
    pad, 60min horizon, dt=10min (T=6 slots), sigma=0.20.
    Manual calc: rate/slot = 200W*10min/60/90Wh = 0.37037 SoC/slot.
    S0=0.20, target=0.60 -> 1 slot gives 0.57037 (short), 2 slots gives
    0.94074 (sufficient) -> each drone needs exactly 2 charging slots.
    4 drones x 2 slots = 8 total pad-slots, and 2 pads x 6 slots = 12
    available, so feasible with room to spare -> optimal objective = 8."""
    r = solve_charge_schedule_milp(
        n_drones=4, pads=[1, 1], S0=[0.20] * 4, required_soc=[0.60] * 4,
        deadline_slot=[6] * 4, horizon_min=60, dt_min=10,
        battery_wh=90.0, station_rate_w=200.0, sigma=0.20)
    assert r["status"] == "Optimal"
    assert r["objective"] == 8.0
    for i in range(4):
        n_charged = sum(r["x"][(i, j, t)] for j in range(2) for t in range(r["T"]))
        assert n_charged == 2
        assert r["S"][(i, 6)] >= 0.60 - 1e-6


def test_pad_capacity_never_exceeded():
    r = solve_charge_schedule_milp(
        n_drones=4, pads=[1, 1], S0=[0.20] * 4, required_soc=[0.60] * 4,
        deadline_slot=[6] * 4, horizon_min=60, dt_min=10,
        battery_wh=90.0, station_rate_w=200.0, sigma=0.20)
    for j in range(2):
        for t in range(r["T"]):
            occ = sum(r["x"][(i, j, t)] for i in range(4))
            assert occ <= 1


def test_soc_bounds_respected():
    r = solve_charge_schedule_milp(
        n_drones=4, pads=[1, 1], S0=[0.20] * 4, required_soc=[0.60] * 4,
        deadline_slot=[6] * 4, horizon_min=60, dt_min=10,
        battery_wh=90.0, station_rate_w=200.0, sigma=0.20)
    for i in range(4):
        for t in range(r["T"] + 1):
            assert 0.20 - 1e-6 <= r["S"][(i, t)] <= 1.0 + 1e-6


def test_infeasible_instance_reported_as_such():
    """Too little capacity/time to meet an aggressive deadline should come
    back infeasible, not silently wrong."""
    r = solve_charge_schedule_milp(
        n_drones=4, pads=[1, 1], S0=[0.20] * 4, required_soc=[0.99] * 4,
        deadline_slot=[1] * 4,  # only 1 slot to go from 0.20 to 0.99 -- impossible
        horizon_min=60, dt_min=10, battery_wh=90.0, station_rate_w=200.0, sigma=0.20)
    assert r["status"] == "Infeasible"


def test_charging_past_full_saturates_instead_of_infeasible():
    """Regression test for a real bug: with S<=S+inc as an == equality, any
    charging decision that would physically overshoot 100% made the whole
    system infeasible instead of saturating (caught by fixing x to a
    known-feasible heuristic solution and finding the MILP still called it
    infeasible). A drone very close to full, with only one (large) charging
    increment available, must still be able to charge and simply cap at
    1.0."""
    r = solve_charge_schedule_milp(
        n_drones=1, pads=[1], S0=[0.95], required_soc=[0.97],
        deadline_slot=[1], horizon_min=10, dt_min=10,
        battery_wh=90.0, station_rate_w=200.0, sigma=0.20)
    # rate/slot = 0.37037, so one slot from 0.95 would "want" to reach 1.32
    # -- must saturate at 1.0, not report infeasible.
    assert r["status"] == "Optimal"
    assert r["S"][(0, 1)] <= 1.0 + 1e-6
    assert r["S"][(0, 1)] >= 0.97 - 1e-6


def test_single_drone_single_station_minimal_case():
    """1 drone, 1 station, needs 1 slot's worth of charge -- simplest
    possible case, exact answer known by construction."""
    r = solve_charge_schedule_milp(
        n_drones=1, pads=[1], S0=[0.20], required_soc=[0.50],
        deadline_slot=[6], horizon_min=60, dt_min=10,
        battery_wh=90.0, station_rate_w=200.0, sigma=0.20)
    assert r["status"] == "Optimal"
    # rate/slot=0.37037; 1 slot -> 0.57037 >= 0.50, sufficient
    assert r["objective"] == 1.0


def test_ccv_matches_v1_within_a_single_band():
    """When nobody needs to cross a CC-CV band boundary, the piecewise
    version must reproduce v1's flat-200W-rate result exactly (the
    hand-checkable instance stays within the 0-70% band throughout)."""
    r = solve_charge_schedule_milp_ccv(
        n_drones=4, pads=[1, 1], S0=[0.20] * 4, required_soc=[0.60] * 4,
        deadline_slot=[6] * 4, horizon_min=60, dt_min=10, battery_wh=90.0, sigma=0.20)
    assert r["status"] == "Optimal"
    assert r["objective"] == 8.0
    for i in range(4):
        assert r["S"][(i, 6)] >= 0.60 - 1e-6


def test_ccv_soc_monotone_non_decreasing():
    """Regression test for a real bug: without an explicit monotonicity
    constraint, CBC found a physically nonsensical solution where SoC
    dropped between slots with no charging and no discharge model to
    explain it (same objective value, just an arbitrary degenerate
    trajectory among several optima). This model has no discharge
    component, so SoC must never decrease."""
    r = solve_charge_schedule_milp_ccv(
        n_drones=1, pads=[1], S0=[0.60], required_soc=[0.95], deadline_slot=[12],
        horizon_min=120, dt_min=10, battery_wh=90.0, sigma=0.20)
    assert r["status"] == "Optimal"
    socs = [r["S"][(0, t)] for t in range(r["T"] + 1)]
    for a, b in zip(socs, socs[1:]):
        assert b >= a - 1e-9


def test_ccv_never_allows_charging_for_free():
    """Regression test for a real bug: without a constraint tying S[i,t+1]
    to S[i,t] when not charging, the Big-M band-selection constraints were
    ALL simultaneously relaxed whenever x_total=0, letting SoC jump to any
    value for free with zero charging sessions (objective=0 on an instance
    that needs real charging)."""
    r = solve_charge_schedule_milp_ccv(
        n_drones=4, pads=[1, 1], S0=[0.20] * 4, required_soc=[0.60] * 4,
        deadline_slot=[6] * 4, horizon_min=60, dt_min=10, battery_wh=90.0, sigma=0.20)
    assert r["objective"] > 0
    for i in range(4):
        n_charged = sum(r["x"][(i, j, t)] for j in range(2) for t in range(r["T"]))
        assert n_charged > 0


def test_ccv_requires_at_least_as_much_charging_as_flat_rate_v1():
    """Crossing into the slower CC-CV bands (120W, 50W) can only need the
    same or MORE pad-time than v1's optimistic constant-200W assumption,
    never less -- the piecewise curve is strictly more realistic/
    restrictive above 70% SoC."""
    r_v1 = solve_charge_schedule_milp(
        n_drones=1, pads=[1], S0=[0.60], required_soc=[0.95], deadline_slot=[12],
        horizon_min=120, dt_min=10, battery_wh=90.0, station_rate_w=200.0, sigma=0.20)
    r_ccv = solve_charge_schedule_milp_ccv(
        n_drones=1, pads=[1], S0=[0.60], required_soc=[0.95], deadline_slot=[12],
        horizon_min=120, dt_min=10, battery_wh=90.0, sigma=0.20)
    assert r_v1["status"] == "Optimal"
    assert r_ccv["status"] == "Optimal"
    assert r_ccv["objective"] >= r_v1["objective"]
