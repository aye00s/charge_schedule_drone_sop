"""REMEDIATION.md Section 5's deterministic-prediction test: 'in the Phase 4
simulator with no randomness after dispatch, the W_j predicted at
reservation time must equal the realised wait for every drone' (tolerance:
one time step). Any mismatch is a bug -- this directly tests the project's
central claim that W_j is exact in a scheduled system, not an estimate.

2026-09-22 checkpoint-4 rework: repointed from the old standalone
sim.ours_policy.run_mission_sim_ours (deleted) to
sim.mission_sim.run_mission_sim(policy='ours', ...) -- this file now
actually tests "the Phase 4 simulator" as REMEDIATION.md Section 5
requires, not a separate parallel engine.

2026-09-22, same day: tolerance tightened from 1.0 (one tick) to 0.0
(exact) after the 1-tick tolerance was found to be masking a real bug,
not just discretization noise. The signed (not absolute) distribution of
realised-predicted across all 812 sessions of the scenario below was
ENTIRELY non-negative (realised always >= predicted, never earlier) and
bimodal: a continuous smear across (0, 1) from raw travel/charge times
never having been rounded to the engine's tick grid, plus a hard pileup
of 252/812 (31%) sessions at EXACTLY +1.0 tick, all of them cases where
the predicted start coincided with an exact tick multiple (commonly: a
drone re-dispatched to the SAME station it had just finished charging
at, tau_ij=0 exactly). Root cause: F7/F9's predicted times were computed
from raw continuous travel time and charge duration (F4), but this
engine can only ever register a state change at t+DT_MIN, never at a
fractional or "same-tick" t -- so a continuous prediction systematically
understated the tick the engine would actually use. Fixed in
sim/mission_sim.py by quantizing travel time and charge duration up to
the tick grid (_ceil_to_tick, with a DT_MIN floor so even a same-tick,
zero-distance dispatch is predicted to take its true minimum one tick)
before they feed F7/F8/F9's calculations -- not by loosening the test,
and not by touching the continuous math in sim/formulas.py itself, which
stays pure. Predicted now matches realised exactly
in every session of the scenario below (794/794 after the fix; the
session count itself shifts slightly from 812 because quantization
changes some F8 station-ranking ties, which is expected)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.mission_sim import run_mission_sim

STATIONS = [(300, 300), (1700, 300), (1000, 1000), (300, 1700), (1700, 1700)]


def test_predicted_start_matches_realised_start_for_every_session():
    r = run_mission_sim(policy="ours", n_uavs=15, station_positions=STATIONS, pads_per_station=2,
                         horizon_min=1000, seed=1, mission_rate_per_min=0.6)
    assert len(r["session_log"]) > 10, "need a meaningful number of sessions to test this"
    mismatches = []
    for cs in r["session_log"]:
        diff = cs["realised_start"] - cs["predicted_start"]
        if abs(diff) > 1e-9:  # exact match required, not "within one tick"
            mismatches.append((cs["uav"], cs["predicted_start"], cs["realised_start"], diff))
    assert not mismatches, f"predicted vs realised start mismatches (must be 0): {mismatches[:5]}"


def test_predicted_start_matches_with_priority_ablation_off():
    """The prediction guarantee must hold regardless of service order,
    since F7's free_time bookkeeping doesn't depend on use_priority."""
    r = run_mission_sim(policy="ours", n_uavs=15, station_positions=STATIONS, pads_per_station=2,
                         horizon_min=1000, seed=1, mission_rate_per_min=0.6,
                         use_priority=False)
    mismatches = [cs for cs in r["session_log"]
                  if abs(cs["realised_start"] - cs["predicted_start"]) > 1e-9]
    assert not mismatches, f"mismatches with use_priority=False: {mismatches[:5]}"
