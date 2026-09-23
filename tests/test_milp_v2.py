"""REMEDIATION.md checkpoint 7: E8 (F13, exact within-slot CC-CV), E9
(dwell-window truncation, found already correct), and MILP v2 (Section 4,
the real F12 objective replacing v1's constant-objective structure)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.energy import CHARGE_BANDS, soc_after_charging
from sim.milp import (f13_pieces_for_band, solve_charge_schedule_milp_ccv,
                       solve_charge_schedule_milp_v2, solve_charge_schedule_ours_v2)


def test_E8_f13_pieces_match_soc_after_charging_on_fine_grid():
    """E8's own pass criterion: for each starting SoC on a fine grid, the
    MILP's maximum next-slot SoC (min of F13's pieces) must equal
    soc_after_charging(S, dt) within 1e-6. Checked across several
    battery/dt combinations, including ones that cross more than one band
    boundary within a single slot."""
    max_err = 0.0
    for battery_wh, dt_min in [(90.0, 10.0), (60.0, 25.0), (120.0, 5.0), (90.0, 45.0)]:
        for band_idx, (lo, hi, rate) in enumerate(CHARGE_BANDS):
            pieces = f13_pieces_for_band(band_idx, dt_min, battery_wh)
            for S in np.linspace(lo, hi - 1e-9, 300):
                true_val = soc_after_charging(S, dt_min, battery_wh)
                pred = min(a * S + b for a, b in pieces)
                max_err = max(max_err, abs(pred - true_val))
    assert max_err < 1e-6, f"F13 pieces deviate from soc_after_charging by {max_err}"


def test_E8_ccv_milp_uses_f13_and_does_not_overshoot_a_band():
    """Regression for the exact bug E8 describes: dt_min=10, battery=90 --
    a drone starting a slot at 69% (near band 0/1's 70% boundary) must NOT
    be able to add ~37% SoC (the single-rate bug's signature); the true
    F13-correct increment for one slot from 69% is bounded by
    soc_after_charging(0.69, 10, 90)."""
    true_next = soc_after_charging(0.69, 10.0, 90.0)
    r = solve_charge_schedule_milp_ccv(n_drones=1, pads=[1], S0=[0.69], required_soc=[0.20],
                                        deadline_slot=[1], horizon_min=10, dt_min=10,
                                        battery_wh=90.0, time_limit_sec=30)
    # required_soc is already met at S0, so the MILP is free to charge or
    # not -- force it to charge by raising required_soc instead, then check
    # the achieved S[i,1] never exceeds the true one-slot ceiling.
    r2 = solve_charge_schedule_milp_ccv(n_drones=1, pads=[1], S0=[0.69], required_soc=[true_next],
                                         deadline_slot=[1], horizon_min=10, dt_min=10,
                                         battery_wh=90.0, time_limit_sec=30)
    assert r2["status"] == "Optimal"
    assert r2["S"][(0, 1)] <= true_next + 1e-6, (
        f"MILP let S overshoot the true F13 ceiling: {r2['S'][(0, 1)]} > {true_next}")


def test_E9_dwell_window_already_truncated_at_horizon():
    """E9's own pass criterion: a drone that needs exactly one slot in the
    FINAL slot must be feasible, even with min_dwell_slots > the number of
    slots actually remaining. Found already correct on inspection (the
    existing `range(t, min(T, t + min_dwell_slots))` already bounds by T)
    -- this test makes that permanent rather than leaving it unverified."""
    r = solve_charge_schedule_milp_ccv(n_drones=1, pads=[1], S0=[0.60], required_soc=[0.62],
                                        deadline_slot=[3], horizon_min=30, dt_min=10,
                                        min_dwell_slots=3, time_limit_sec=30)
    assert r["status"] == "Optimal"
    assert r["x"][(0, 0, 2)] == 1


def test_milp_v2_hand_checkable_instance():
    """REMEDIATION.md Section 4's required hand-checkable instance: 2
    drones, 1 station/1 pad, 2 missions, dt=10min, battery=90Wh, both
    drones start at S0=sigma=0.20 (need to charge before either can fly).

    By hand: each mission needs 9Wh (0.10 SoC) on top of sigma reserve, so
    a drone must reach S=0.30 before departing. Charging at band 0's 200W
    from 0.20 to 0.30 needs 0.10*90=9Wh, time=9/200*60=2.7min -> 1 slot
    (10min) suffices. With 1 pad, sessions are sequential: drone0 charges
    slot 0 (S 0.20->0.30), flies slots 1-2 (finishes at t=30min); drone1
    charges slot 1 (S 0.20->0.30), flies slots 2-3 (finishes at t=40min).
    Cmax=40min, no tardiness (deadline=60min), energy_cost = tariff_flat *
    2 sessions * 9Wh = 0.15*18 = 2.7. Z = 1*40 + 1*2.7 + 1*0 = 42.7."""
    missions = [
        dict(duration_slots=2, energy_wh=9.0, release_slot=0, deadline_min=60.0),
        dict(duration_slots=2, energy_wh=9.0, release_slot=0, deadline_min=60.0),
    ]
    r = solve_charge_schedule_milp_v2(n_drones=2, pads=[1], S0=[0.20, 0.20], missions=missions,
                                       battery_wh=90.0, horizon_min=60, dt_min=10,
                                       alpha=1.0, beta=1.0, gamma=1.0, tariff_flat=0.15,
                                       time_limit_sec=60)
    assert r["status"] == "Optimal"
    assert abs(r["objective"] - 42.7) < 1e-6
    assert r["Cmax"] == 40.0
    assert r["gamma_tardy_term"] == 0.0


def test_ours_v2_reuses_formulas_and_shows_a_real_nonzero_gap():
    """Addition 2 (2026-09-23): the discretised heuristic must reuse
    sim/formulas.py's own functions, verified here by a real, hand-
    explainable gap on the SAME hand-checkable instance as the MILP test
    above: F6's target_soc floor (recharge_trigger + 0.05 = 0.40) makes the
    heuristic charge to 0.40 instead of the MILP's exact-minimum 0.30,
    costing extra energy for no schedule benefit (Cmax is unaffected,
    since 0.40 is still reached within the same 1 slot). Gap is entirely
    attributable to this documented, real behavioural difference -- not
    tuned away, not a bug in either solver."""
    missions = [
        dict(duration_slots=2, energy_wh=9.0, release_slot=0, deadline_min=60.0),
        dict(duration_slots=2, energy_wh=9.0, release_slot=0, deadline_min=60.0),
    ]
    r_milp = solve_charge_schedule_milp_v2(n_drones=2, pads=[1], S0=[0.20, 0.20], missions=missions,
                                            battery_wh=90.0, horizon_min=60, dt_min=10, time_limit_sec=60)
    r_heur = solve_charge_schedule_ours_v2(n_drones=2, pads=[1], S0=[0.20, 0.20], missions=missions,
                                            battery_wh=90.0, horizon_min=60, dt_min=10)
    assert r_heur["status"] == "Heuristic"  # feasible, all missions done
    assert r_heur["Cmax"] == r_milp["Cmax"]  # same schedule length
    assert r_heur["beta_energy_term"] > r_milp["beta_energy_term"]  # the real, explained gap
    gap = (r_heur["objective"] - r_milp["objective"]) / r_milp["objective"]
    assert 0.0 < gap < 0.10  # a real but modest gap (~6.3%), not a blowup
