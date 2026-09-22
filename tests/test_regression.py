"""REMEDIATION.md Section 5: 'Existing Phase 1/2 validation and both Phase
3 sanity checks (slack-zero reduction, Kleinrock conservation) still pass
after all changes.' Re-runs those checks directly (importing the existing
test functions rather than forking a second copy of their logic) plus a
new requirement added at checkpoint 4: policy='baseline' must reproduce
the exact pre-refactor Phase 4/6 outputs for fixed seeds, so adding the
`policy` parameter changed nothing about existing behaviour.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.mission_sim import run_mission_sim
# Aliased on import (not `test_*`) so pytest doesn't also collect these as
# second, duplicate top-level items in THIS file -- they're invoked below,
# not re-collected.
from tests.test_phase1 import test_table2_within_tolerance as _table2_check
from tests.test_phase1 import test_table3_within_tolerance as _table3_check
from tests.test_phase2 import test_simulator_matches_analytics as _phase2_check
from tests.test_phase3_sanity import \
    test_conservation_r2_matches_r1_on_averages as _conservation_check
from tests.test_phase3_sanity import \
    test_slack_zero_reduction_matches_phase2_analytics as _slack_zero_check


def test_phase1_tables_still_validate():
    _table2_check()
    _table3_check()


def test_phase2_simulator_still_matches_analytics():
    _phase2_check()


def test_phase3_slack_zero_sanity_check_still_passes():
    _slack_zero_check()


def test_phase3_conservation_sanity_check_still_passes():
    _conservation_check()


# --- Golden reference values, captured from run_mission_sim (pre-checkpoint-4,
# before the `policy` parameter existed) on 2026-09-22, via
#   python -c "from sim.mission_sim import run_mission_sim; ..."
# run against the UNMODIFIED code, one config at a time, immediately before
# starting the checkpoint-4 refactor. See CLAUDE.md Section 13's checkpoint
# 4 report for the exact capture commands.
STATIONS = [(300, 300), (1700, 300), (1000, 1000), (300, 1700), (1700, 1700)]

_GOLDEN_CONFIGS = [
    (
        dict(n_uavs=10, station_positions=STATIONS, pads_per_station=2, horizon_min=300,
             seed=1, mission_rate_per_min=0.3),
        dict(missions_total=77, missions_completed=76, tardy_count=0, total_tardiness_min=0,
             safety_violations=0, makespan_min=300.0, charge_sessions=10,
             total_charge_energy_wh=662.8119520201813, total_charge_cost_usd=0.11058845936922176,
             mean_charge_duration_min=31.1),
    ),
    (
        dict(n_uavs=10, station_positions=STATIONS, pads_per_station=2, horizon_min=300,
             seed=7, mission_rate_per_min=0.3, charge_policy="adaptive", order="priority",
             pad_order="margin"),
        dict(missions_total=86, missions_completed=86, tardy_count=0, total_tardiness_min=0,
             safety_violations=0, makespan_min=293.0, charge_sessions=51,
             total_charge_energy_wh=746.1962623627262, total_charge_cost_usd=0.11542943935440901,
             mean_charge_duration_min=3.8627450980392157),
    ),
    (
        dict(n_uavs=15, station_positions=STATIONS, pads_per_station=2, horizon_min=500,
             seed=3, mission_rate_per_min=0.6, tariff="tou"),
        dict(missions_total=309, missions_completed=309, tardy_count=0, total_tardiness_min=0,
             safety_violations=0, makespan_min=499.0, charge_sessions=44,
             total_charge_energy_wh=2952.074978421623, total_charge_cost_usd=0.2853571008944442,
             mean_charge_duration_min=31.318181818181817),
    ),
]


def test_mission_list_identical_across_policies_and_ablations_at_fixed_seed():
    """X3's whole comparison depends on baseline/jsq/ours (and every ours
    ablation) facing the EXACT SAME missions (release times, destinations,
    deadlines) at a given seed -- otherwise 'use_queue_term=False isolates
    the W_j term' isn't true, since the policies would also be comparing
    against different demand. Mission generation is a single shared code
    block in run_mission_sim, run before any policy branch, so this should
    hold architecturally; this test checks it holds in practice, across
    every policy and every one of the six ablation flags individually."""
    kwargs = dict(n_uavs=10, station_positions=STATIONS, pads_per_station=2, horizon_min=300,
                  seed=1, mission_rate_per_min=0.3)
    reference = run_mission_sim(policy="baseline", **kwargs)
    ref_key = (reference["mission_release_times"], reference["mission_destinations"],
               reference["mission_deadlines"])
    assert len(reference["mission_release_times"]) > 5, "need a non-trivial mission list to test this"

    variants = [
        ("jsq", dict(policy="jsq")),
        ("ours (defaults)", dict(policy="ours")),
        ("ours, use_queue_term=False", dict(policy="ours", use_queue_term=False)),
        ("ours, use_reservation=False", dict(policy="ours", use_reservation=False)),
        ("ours, use_priority=False", dict(policy="ours", use_priority=False)),
        ("ours, use_partial=False", dict(policy="ours", use_partial=False)),
        ("ours, use_jit=True", dict(policy="ours", use_jit=True)),
        ("ours, use_charge_time_term=False", dict(policy="ours", use_charge_time_term=False)),
    ]
    for label, extra in variants:
        r = run_mission_sim(**kwargs, **extra)
        key = (r["mission_release_times"], r["mission_destinations"], r["mission_deadlines"])
        assert key == ref_key, f"{label}: mission list diverged from baseline's at the same seed"


def test_policy_baseline_routes_to_nearest_reachable_station():
    """Confirms, rather than just asserts from reading the code, that
    policy='baseline' (B1/B2) picks the station by DISTANCE, not by list
    order -- stations are listed deliberately out of distance order
    (1500m, 1000m, 500m from the drone) so a list-order bug would be
    caught, not just a distance-sort bug."""
    stations = [(1500.0, 0.0), (1000.0, 0.0), (500.0, 0.0)]  # index 2 is nearest
    r = run_mission_sim(policy="baseline", n_uavs=1, station_positions=stations,
                         pads_per_station=1, horizon_min=40, seed=1, mission_rate_per_min=0.0,
                         initial_soc=0.30, initial_positions=[(0.0, 0.0)])
    assert len(r["session_log"]) == 1
    assert r["session_log"][0]["station"] == 2, (
        f"expected the nearest station (index 2, 500m away), got {r['session_log'][0]['station']}")


def test_policy_baseline_reproduces_pre_checkpoint4_outputs_exactly():
    """The whole point of making 'baseline' the default and gating every
    new parameter behind it (policy, and the ours-only/baseline-only
    validation) is that adding them must change NOTHING for existing
    callers. Every field below must match bit-for-bit (== not
    approximately), across three configs that between them exercise every
    pre-existing parameter (charge_policy full/adaptive, order fcfs/
    priority, pad_order fcfs/margin, tariff flat/tou)."""
    for kwargs, golden in _GOLDEN_CONFIGS:
        r = run_mission_sim(policy="baseline", **kwargs)
        for key, expected in golden.items():
            assert r[key] == expected, (
                f"policy='baseline' no longer reproduces the pre-checkpoint-4 output: "
                f"{key} = {r[key]!r}, expected {expected!r} (config: {kwargs})")
