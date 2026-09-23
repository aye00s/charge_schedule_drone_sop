"""REMEDIATION.md Section 5: one test per formula (F4-F11 here; F9's
stampede test and F14's JIT test need the full engine, see
test_ours_policy.py)."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from sim.energy import flight_energy_wh, time_to_reach_target_min
from sim.formulas import (charging_slack, combined_priority, deterministic_wait,
                           margin, objective_F12, station_gate, target_soc, time_to_ready_cost)
from sim.mission_sim import BATTERY_WH, RECHARGE_TRIGGER_SOC, SIGMA, _distance, run_mission_sim
from sim.tariff import FLAT_RATE_USD_PER_WH


def test_F4_time_to_reach_target_matches_band_sum_across_boundaries():
    B = 90.0
    # crossing both boundaries: 0.5 -> 0.95 spans band1(0-0.7,200W), band2(0.7-0.9,120W), band3(0.9-1.0,50W)
    t_direct = time_to_reach_target_min(0.5, 0.95, B)
    t_bandsum = (
        (0.7 - 0.5) * B / 200.0 * 60.0 +
        (0.9 - 0.7) * B / 120.0 * 60.0 +
        (0.95 - 0.9) * B / 50.0 * 60.0
    )
    assert abs(t_direct - t_bandsum) < 1e-9


def test_F5_station_gate_refuses_and_accepts_correctly():
    B = 90.0
    # far station (unreachable): 2000m needs 2000*0.01/90=0.222 soc, at soc=0.25 -> 0.25-0.222=0.028 < sigma=0.20 -> refused
    far_stations = [(2000, 0)]
    gate = station_gate((0, 0), far_stations, soc=0.25, battery_wh=B)
    assert gate == []
    # near station (reachable): 100m needs 100*0.01/90=0.0011 soc, at soc=0.25 -> plenty of margin
    near_stations = [(100, 0)]
    gate2 = station_gate((0, 0), near_stations, soc=0.25, battery_wh=B)
    assert gate2 == [0]


def test_F6_target_soc_never_below_floor_or_above_one():
    for s_req in [-0.5, 0.0, 0.1, 0.5, 2.0]:
        tgt = target_soc(s_req, RECHARGE_TRIGGER_SOC)
        assert tgt <= 1.0
        assert tgt >= RECHARGE_TRIGGER_SOC + 0.05 - 1e-9


def test_F7_deterministic_wait_matches_free_time_example():
    # pads free at [10, 25], t_arr=5 -> earliest pad frees at 10, wait=10-5=5
    W, start, pad = deterministic_wait([10.0, 25.0], t_arr=5.0)
    assert abs(W - 5.0) < 1e-9
    assert start == 10.0
    assert pad == 0
    # t_arr=30 -> both pads already free (10,25 < 30) -> wait=0, start=t_arr
    W2, start2, pad2 = deterministic_wait([10.0, 25.0], t_arr=30.0)
    assert W2 == 0.0
    assert start2 == 30.0


def test_F8_far_empty_beats_near_busy_when_times_say_so():
    B = 90.0
    # Station A: 500m away (tau_A ~ 0.56 min at 15m/s), but 3 reservations
    # queued such that the earliest free pad is at t=50.
    # Station B: 2000m away (tau_B ~ 2.22 min), empty queue (free at t=0).
    tau_A_min = (500 / 15.0) / 60.0
    tau_B_min = (2000 / 15.0) / 60.0
    t = 0.0
    J_A, _, _, _ = time_to_ready_cost(tau_A_min, [50.0], t, s_arr=0.3, s_tgt=0.5, battery_wh=B)
    J_B, _, _, _ = time_to_ready_cost(tau_B_min, [0.0], t, s_arr=0.3, s_tgt=0.5, battery_wh=B)
    assert J_B < J_A, "the far-but-empty station must win when its total time-to-ready is lower"


def test_F10_charging_slack_cap_and_computation():
    slack_cap = 1000.0
    assert charging_slack(None, t=0.0, flight_time_min=5.0, slack_cap=slack_cap) == slack_cap
    s = charging_slack(next_mission_deadline=100.0, t=10.0, flight_time_min=5.0, slack_cap=slack_cap)
    assert abs(s - 85.0) < 1e-9  # 100 - (10+5)


def test_F11_infinity_rule_and_ranking():
    t_ref = 39.0
    # slack<=0 -> +inf (feasibility emergency, handled first)
    assert combined_priority(slack=0.0, margin_val=0.5, w1=1, w2=1, t_ref=t_ref) == math.inf
    assert combined_priority(slack=-5.0, margin_val=0.5, w1=1, w2=1, t_ref=t_ref) == math.inf
    # margin<=0 -> +inf
    assert combined_priority(slack=10.0, margin_val=0.0, w1=1, w2=1, t_ref=t_ref) == math.inf
    # normal case: smaller slack -> higher (more urgent) priority
    p_urgent = combined_priority(slack=2.0, margin_val=0.3, w1=1, w2=1, t_ref=t_ref)
    p_relaxed = combined_priority(slack=50.0, margin_val=0.3, w1=1, w2=1, t_ref=t_ref)
    assert p_urgent > p_relaxed
    assert math.isfinite(p_urgent) and math.isfinite(p_relaxed)


def test_F11_no_division_errors_at_extremes():
    t_ref = 39.0
    # tiny but POSITIVE slack/margin don't trigger the +inf rule (which is
    # strictly slack<=0 or margin<=0) -- they must instead be caught by the
    # eps floors (eps_t=1.0, eps_s=0.01) and produce a finite result, not
    # a division blowup.
    p = combined_priority(slack=1e-12, margin_val=1e-12, w1=1, w2=1, t_ref=t_ref)
    assert math.isfinite(p)


def test_F12_objective_normalizes_three_terms_correctly():
    """Hand-picked numbers: makespan=50 of horizon=100 -> C_max term=0.5;
    energy_cost=$0.03 against 1000 Wh mission energy at the flat rate
    (1000*FLAT_RATE=$0.15) -> energy term=0.03/0.15=0.2; tardiness=90min
    over 10 missions * 45min mean duration=450 -> tardy term=0.2. With
    alpha=beta=gamma=1, Z = 0.5+0.2+0.2 = 0.9."""
    Z, c, e, td = objective_F12(makespan_min=50.0, horizon_min=100.0, total_cost_usd=0.03,
                                 total_mission_flight_energy_wh=1000.0, total_tardiness_min=90.0,
                                 n_missions=10, mean_mission_duration_min=45.0)
    assert abs(c - 0.5) < 1e-9
    assert abs(e - 0.2) < 1e-9
    assert abs(td - 0.2) < 1e-9
    assert abs(Z - 0.9) < 1e-9
    # zero denominators must yield 0.0 terms, not a ZeroDivisionError
    Z0, c0, e0, td0 = objective_F12(makespan_min=0.0, horizon_min=0.0, total_cost_usd=0.0,
                                     total_mission_flight_energy_wh=0.0, total_tardiness_min=0.0,
                                     n_missions=0, mean_mission_duration_min=45.0)
    assert (Z0, c0, e0, td0) == (0.0, 0.0, 0.0, 0.0)


def test_F12_total_mission_energy_excludes_charger_trips():
    """REMEDIATION.md checkpoint-4 rule (added 2026-09-22, per user
    instruction): total_mission_energy must be mission-FLIGHT energy only,
    excluding charger-trip legs. Two hand-built scenarios in
    sim.mission_sim.run_mission_sim, both with a single UAV starting
    co-located with initial_positions (so the RNG stream's only draws are
    the mission generator's, letting the expected energy be replicated
    independently rather than guessed):

    (a) mission_rate_per_min=0 (no missions ever exist) but initial_soc is
        forced below the recharge trigger, so the UAV takes exactly one
        real, non-trivial charger trip and a real charging session
        completes. mission_flight_energy_wh must be exactly 0.0 even
        though real flight energy (to and from the station) and real
        charge energy were both spent.
    (b) mission_rate_per_min > 0 with initial_soc=1.0 and a horizon short
        enough that the two generated missions complete without ever
        dropping the UAV's SoC to the recharge trigger (verified: 0
        charge sessions). mission_flight_energy_wh must equal the sum of
        flight_energy_wh() over the exact mission legs, independently
        recomputed here by replicating the same RNG draws
        run_mission_sim uses internally (uniform position draw skipped
        because initial_positions is given, so the first draws are the
        mission generator's exponential/uniform pairs, in that order)."""
    # (a) charger-trip-only: mission_flight_energy_wh must be exactly 0.0
    r_a = run_mission_sim(policy="baseline", n_uavs=1, station_positions=[(500.0, 0.0)],
                           pads_per_station=1, horizon_min=40, seed=1, mission_rate_per_min=0.0,
                           initial_soc=0.30, initial_positions=[(0.0, 0.0)])
    assert r_a["missions_total"] == 0
    assert r_a["charge_sessions"] == 1
    assert r_a["total_charge_energy_wh"] > 0.0
    assert r_a["mission_flight_energy_wh"] == 0.0

    # (b) mission-only: independently replicate the mission-generator RNG
    # draws (initial_positions given -> no position draws consumed first).
    seed, rate, horizon = 123, 0.05, 30.0
    rng = np.random.default_rng(seed)
    t, dests = 0.0, []
    while True:
        t += rng.exponential(1.0 / rate)
        if t > horizon:
            break
        dests.append(tuple(rng.uniform(0, 2000.0, size=2)))
    pos = (0.0, 0.0)
    expected_mission_energy = 0.0
    for d in dests:
        expected_mission_energy += flight_energy_wh(_distance(pos, d))
        pos = d

    r_b = run_mission_sim(policy="baseline", n_uavs=1, station_positions=[(0.0, 0.0)],
                           pads_per_station=1, horizon_min=horizon, seed=seed,
                           mission_rate_per_min=rate, initial_soc=1.0,
                           initial_positions=[(0.0, 0.0)])
    assert r_b["missions_total"] == len(dests) == 2
    assert r_b["missions_completed"] == len(dests)
    assert r_b["charge_sessions"] == 0  # SoC must stay above the trigger throughout
    assert abs(r_b["mission_flight_energy_wh"] - expected_mission_energy) < 1e-9


def test_F12_drain_period_reports_unfinished_at_cap():
    """REMEDIATION.md checkpoint-4 rule (added 2026-09-22): stop releasing
    missions at the horizon but keep advancing ticks (a drain period) until
    all released missions finish or a cap is hit; report how many are
    still unfinished at the cap. horizon_min=20 cuts the run off mid-way
    through the second of two generated missions (same seed/rate as the
    energy test above -- second mission is assigned around t=19 and needs
    ~2 ticks, past the horizon=20 cutoff): with drain_cap_min=0 (default,
    no drain) it must be left incomplete; with a generous drain_cap_min it
    must finish and unfinished_at_cap must drop to 0."""
    kwargs = dict(policy="baseline", n_uavs=1, station_positions=[(0.0, 0.0)],
                  pads_per_station=1, horizon_min=20.0, seed=123, mission_rate_per_min=0.05,
                  initial_soc=1.0, initial_positions=[(0.0, 0.0)])
    r_no_drain = run_mission_sim(drain_cap_min=0.0, **kwargs)
    assert r_no_drain["missions_total"] == 2
    assert r_no_drain["missions_completed"] == 1
    assert r_no_drain["unfinished_at_cap"] == 1

    r_drained = run_mission_sim(drain_cap_min=10.0, **kwargs)
    assert r_drained["missions_total"] == 2
    assert r_drained["missions_completed"] == 2
    assert r_drained["unfinished_at_cap"] == 0


def test_x5_energy_decomposition_conserves_energy_exactly():
    """X5's energy decomposition (mission flight + station trips + change
    in stored charge) must satisfy an exact conservation identity:
    end_of_run_stored_charge_change_wh == total_charge_energy_ticked_wh
    - mission_flight_energy_wh - station_trip_energy_wh. Found (2026-09-23)
    that using `total_charge_energy_wh` (completed-sessions-only) in this
    identity leaves a real, nonzero gap whenever a drone is still
    mid-charge when the run ends -- drain_cap_min only waits for MISSIONS
    to finish, not charge sessions in progress, so a charging session can
    legitimately outlive the last mission and never get tallied into the
    completed-only field. `total_charge_energy_ticked_wh` (ticks up every
    tick regardless of session completion) closes the identity exactly;
    checked here across all three policies and several fleet sizes,
    deliberately with a drain cap enabled (drain_cap_min=500) so this
    isn't just checked in the no-boundary-effect case."""
    STATIONS = [(300, 300), (1700, 300), (1000, 1000), (300, 1700), (1700, 1700)]
    for policy_kwargs in [dict(policy="baseline"), dict(policy="jsq"), dict(policy="ours")]:
        for n in (2, 5, 10):
            r = run_mission_sim(n_uavs=n, station_positions=STATIONS, pads_per_station=2,
                                 horizon_min=300, seed=1, mission_rate_per_min=0.3,
                                 drain_cap_min=500.0, **policy_kwargs)
            lhs = r["end_of_run_stored_charge_change_wh"]
            rhs = (r["total_charge_energy_ticked_wh"] - r["mission_flight_energy_wh"]
                   - r["station_trip_energy_wh"])
            assert abs(lhs - rhs) < 1e-6, f"{policy_kwargs}, n={n}: identity off by {lhs - rhs}"


def test_mean_on_pad_queue_length_hand_verified():
    """Pre-X3 requirement (2026-09-22): on-pad queue length, time-integrated,
    needed to interpret F14 (JIT should reduce this toward 0 without
    changing total delay). Hand-built, fully deterministic scenario: 2
    drones co-located at 1 station with 1 pad, both needing to charge
    immediately (initial_soc below trigger). Drone 0 gets the pad first
    (charges start_soc=0.3 -> 1.0, 30min, realised_start=1.0); drone 1
    must wait for the pad the whole time drone 0 is charging, entering
    WAITING_FOR_PAD at the same tick drone 0 starts (t=1) and only
    reaching CHARGING at its own realised_start (t=32) -- a wait of
    32-1=31 minutes, during which the on-pad queue length is exactly 1;
    0 at every other tick of the 120-minute horizon. Expected mean =
    31/120."""
    station = [(1000.0, 1000.0)]
    positions = [(1000.0, 1000.0), (1000.0, 1000.0)]
    r = run_mission_sim(policy="ours", n_uavs=2, station_positions=station, pads_per_station=1,
                         horizon_min=120, seed=1, mission_rate_per_min=0.0,
                         initial_soc=0.30, initial_positions=positions)
    assert len(r["session_log"]) == 2
    s0, s1 = sorted(r["session_log"], key=lambda cs: cs["uav"])
    assert s0["realised_start"] == 1.0
    assert s1["realised_start"] == 32.0
    expected_mean = (s1["realised_start"] - s0["realised_start"]) / 120.0
    assert abs(r["mean_on_pad_queue_length"] - expected_mean) < 1e-9


def test_runtime_per_decision_reported_and_sane():
    """Pre-X3 requirement (2026-09-22): wall-clock time around the
    dispatch-decision block only (F7-F11 for 'ours'; the reachability+
    routing loop for baseline/jsq), not the whole tick. Can't hand-verify
    an exact wall-clock value, so this is a sanity/smoke check: positive
    and bounded well below a whole tick's worth of unrelated work when
    dispatches occur, exactly 0.0 when none do (no drones ever needed
    charging)."""
    STATIONS = [(300, 300), (1700, 300), (1000, 1000), (300, 1700), (1700, 1700)]
    r = run_mission_sim(policy="ours", n_uavs=10, station_positions=STATIONS, pads_per_station=2,
                         horizon_min=300, seed=1, mission_rate_per_min=0.3)
    assert len(r["request_times"]) > 0
    assert 0.0 < r["runtime_per_decision_us"] < 100_000.0  # generous upper bound: 100ms/decision

    r_idle = run_mission_sim(policy="baseline", n_uavs=1, station_positions=[(0.0, 0.0)],
                              pads_per_station=1, horizon_min=10, seed=1, mission_rate_per_min=0.0,
                              initial_soc=1.0, initial_positions=[(0.0, 0.0)])
    assert len(r_idle["request_times"]) == 0
    assert r_idle["runtime_per_decision_us"] == 0.0
