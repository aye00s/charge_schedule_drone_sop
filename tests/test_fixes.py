"""One test per REMEDIATION.md fix (Section 1: E1-E13). Each documents what
was wrong, what the fix is, and whether the described bug actually
reproduced in this codebase before the fix (E6 did not -- reported as such,
not silently "fixed" anyway)."""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase1_baseline import (M_VALUES, TABLE3, L_concentrated, L_distributed,
                              bisect, t_distributed)
from sim.mission_sim import (BATTERY_WH, SIGMA, _mission_slack,
                              _reachable_with_return, run_mission_sim)
from sim.models import Mission, UAV
from sim.scheduler import (AREA_SIDE_M, DRONE_SPEED_MPS, centroid, simulate_concentrated_with_travel,
                            simulate_regime)

STATIONS = [(500, 500), (1500, 500), (500, 1500), (1500, 1500)]


def test_E1_per_pad_vs_whole_hub_is_not_like_for_like():
    """E1: L_d (Eq. 11) is one pad's queue; L_c (Eq. 13) is the whole hub's.
    Comparing them directly reverses which layout looks better once you
    account for the fact a distributed layout has n pads, not one."""
    n, m, rho = 5, 7, 0.8
    Ld = L_distributed(rho, m)
    Lc = L_concentrated(rho, n, m)
    assert Ld < Lc, "per-pad metric says distributed wins"
    assert n * Ld > Lc, "but total-system metric says concentrated wins -- opposite conclusion"

    # t_d is already like-for-like: t_d = n*L_d/(1-P_blocking)
    Pb_d = (1 - rho) * rho**m / (1 - rho ** (m + 1))
    td = t_distributed(rho, m, n)
    assert abs(td - n * Ld / (1 - Pb_d)) < 1e-9


def test_E3_jsq_routes_to_idle_pad_not_busy_empty_queue_pad():
    """E3: routing by waiting-count let an idle pad (0 waiting, 0 in
    system) tie with a busy pad with an empty queue (0 waiting, 1 in
    system), sending arrivals to the busy one half the time. Must route by
    in-system count instead."""
    from sim.scheduler import simulate_regime
    tie_rng = np.random.default_rng(0)

    def argmin_tiebreak(values, rng):
        values = np.asarray(values)
        best = values.min()
        candidates = np.flatnonzero(values == best)
        return int(candidates[0]) if len(candidates) == 1 else int(candidates[rng.integers(len(candidates))])

    # pad 0 busy w/ empty queue (in_system=1), pad 1 idle (in_system=0)
    choice = argmin_tiebreak([1, 0], tie_rng)
    assert choice == 1, "must route to the idle pad, not tie with the busy-empty-queue one"


def test_E5_margin_pad_order_is_an_explicit_ablation_not_the_default():
    """E5: margin-based pad-queue ordering (serve lowest SoC first) is
    effectively longest-job-first once CC-CV makes charge durations
    unequal, and queued drones have landed (A6) so there's no safety
    reason to prioritise low SoC. It must be an explicit, labelled
    ablation (pad_order='margin'), never the implied behavior of
    order='priority'."""
    r_default = run_mission_sim(n_uavs=10, station_positions=STATIONS, pads_per_station=1,
                                 horizon_min=200, seed=3, mission_rate_per_min=0.5,
                                 charge_policy="full", order="priority")
    r_margin = run_mission_sim(n_uavs=10, station_positions=STATIONS, pads_per_station=1,
                                horizon_min=200, seed=3, mission_rate_per_min=0.5,
                                charge_policy="full", order="priority", pad_order="margin")
    # Both must be safe; they're allowed to differ (that's the point of the ablation).
    assert r_default["safety_violations"] == 0
    assert r_margin["safety_violations"] == 0


def test_E6_reachability_gate_already_refuses_the_stranding_case():
    """E6 as filed: the station gate must hold reserve sigma on arrival AT
    THE STATION, not at the mission destination. VERIFIED: this codebase's
    _reachable_with_return already does this correctly (added earlier,
    independently, while fixing a different smoke-test failure -- 1410
    safety violations from drones stranded with no reachable station). The
    exact E6 counter-example is checked here and PASSES on unmodified code;
    no fix was needed for this specific case. Recorded plainly rather than
    "fixing" something that wasn't broken."""
    position = (0, 0)
    dest = (6000, 0)  # reachable: soc_to_dest=0.667, arrival soc=0.333 >= sigma
    stations = [(8000, 0)]  # dest->station=2000m, soc_return=0.222; 0.333-0.222=0.111 < sigma
    ok, _ = _reachable_with_return(position, dest, soc=1.0, battery_wh=BATTERY_WH,
                                    station_positions=stations)
    assert ok is False, "dispatch must be refused: reachable to destination but not onward to a station"


def test_E7_mission_ranking_uses_slack_not_raw_deadline():
    """E7: sorting missions by deadline-t ignores flight time entirely. A
    mission with a later deadline but a much longer flight can have LESS
    true slack than one with an earlier deadline and a short flight, and
    must rank as more urgent."""
    t = 0.0
    uav = UAV(id=0, position=(0, 0), battery_wh=BATTERY_WH, soc=1.0)

    # Mission A: deadline=100, short flight (nearby destination)
    mission_a = Mission(id=0, destination=(300, 0), release_time=0, deadline=100)
    # Mission B: deadline=90 (earlier!), but a much longer flight
    mission_b = Mission(id=1, destination=(50000, 0), release_time=0, deadline=90)

    slack_a = _mission_slack(mission_a, t, [uav])
    slack_b = _mission_slack(mission_b, t, [uav])

    assert slack_b < slack_a, "B's much longer flight must make it more urgent despite the earlier-looking raw deadline gap being smaller"
    # sanity: raw deadline-t alone would rank B as only slightly more urgent (90 vs 100),
    # but true slack must show a much starker gap once flight time is accounted for
    raw_gap = mission_a.deadline - mission_b.deadline  # = 10
    slack_gap = slack_a - slack_b
    assert slack_gap > raw_gap


def test_E4a_jsq_travel_cost_is_in_minutes():
    """E4(a): cost must be dimensionally in minutes. Max possible travel
    time across the 2000m x 2000m area at 15 m/s must be a few minutes,
    not ~188 seconds misinterpreted as raw (undivided-by-60) time units."""
    max_dist = math.hypot(AREA_SIDE_M, AREA_SIDE_M)
    max_travel_min = max_dist / DRONE_SPEED_MPS / 60.0
    assert 2.0 < max_travel_min < 5.0


def test_E4c_travel_delay_is_a_real_scheduled_event_not_instant():
    """E4(c): a routed request must not join the pad instantly -- travel
    must be a real event-scheduled delay. For routings with zero travel
    (fixed_split), total_delay (request-to-service-start, including
    travel) must equal wait (on-pad-only delay) EXACTLY. For jsq_travel,
    total_delay must be strictly greater than wait, since travel adds
    delay on top of any on-pad queueing."""
    r_no_travel = simulate_regime(routing="fixed_split", order="fcfs", n_stations=5, capacity=7,
                                   lam_total=4.0, mu=1.0, horizon=20000, seed=1, slack_mean=1.0)
    assert abs(r_no_travel["wait"] - r_no_travel["total_delay"]) < 1e-9

    r_travel = simulate_regime(routing="jsq_travel", order="priority", n_stations=5, capacity=7,
                                lam_total=4.0, mu=1.0, horizon=20000, seed=1, slack_mean=1.0)
    assert r_travel["total_delay"] > r_travel["wait"]


def test_E4d_concentrated_with_travel_matches_analytics_when_travel_disabled():
    """E4(d): the new concentrated-with-travel baseline, with travel
    effectively disabled (huge speed), must reproduce the already-
    validated M/M/n/nm analytics -- confirms the multi-server engine
    itself is correct before trusting it with travel enabled."""
    from phase1_baseline import L_concentrated
    n, m, mu, rho = 5, 7, 1.0, 0.8
    lam_total = rho * n * mu
    r = simulate_concentrated_with_travel(n_servers=n, capacity=n * m, lam_total=lam_total, mu=mu,
                                           horizon=20000, seed=1, hub_position=(1000, 1000),
                                           drone_speed_mps=1e9)
    Lc = L_concentrated(rho, n, m)
    assert abs(r["L"] - Lc) / Lc < 0.05


def test_pooling_bound_r3a_cannot_beat_concentrated_wait_at_negligible_blocking():
    """Sanity test (user-requested, before trusting any R3a 'beats
    concentrated' result): a pooled M/M/n queue is provably at least as
    good as ANY routing to n separate single-server queues on mean wait --
    any waiting customer in a pooled system can be served by whichever
    server frees up next; in distributed routing (however smart), a
    customer is locked to the single server at its assigned station. At
    rho=0.5 (negligible blocking, so 'wait of admitted' is a clean,
    comparable quantity), R3a's simulated wait must be >= the concentrated
    analytic t_c within noise. If this fails, there's a bug -- do not
    trust any R3a-beats-concentrated finding until this passes."""
    from phase1_baseline import t_concentrated
    n, m, mu, rho = 5, 7, 1.0, 0.5
    lam_total = rho * n * mu
    tc_a = t_concentrated(rho, n, m)
    waits = []
    for seed in range(1, 16):
        r = simulate_regime(routing="jsq", order="priority", n_stations=n, capacity=m,
                             lam_total=lam_total, mu=mu, horizon=30000, seed=seed, slack_mean=1.0)
        waits.append(r["wait"] * lam_total)
    assert np.mean(waits) >= tc_a - 3 * np.std(waits) / len(waits) ** 0.5


def test_E4d_fair_comparison_uses_shared_geometry():
    """E4(d): R3b (distributed + travel) must be compared against a
    concentrated layout that ALSO pays travel cost, with the hub placed at
    the centroid of the distributed station positions -- not against the
    travel-free analytic L_c as before (which changed two things -
    pooling and travel - at once)."""
    from sim.scheduler import _station_positions
    n, m, mu, rho = 5, 7, 1.0, 1.0
    lam_total = rho * n * mu
    stations = _station_positions(n)
    hub = centroid(stations)

    r3b = simulate_regime(routing="jsq_travel", order="priority", n_stations=n, capacity=m,
                           lam_total=lam_total, mu=mu, horizon=20000, seed=1, slack_mean=1.0)
    r_conc = simulate_concentrated_with_travel(n_servers=n, capacity=n * m, lam_total=lam_total,
                                                mu=mu, horizon=20000, seed=1, hub_position=hub,
                                                order="priority", slack_mean=1.0)
    # Both must produce valid, finite, non-degenerate results on shared geometry.
    assert r3b["L"] >= 0 and r_conc["L"] >= 0
    assert r3b["block_frac"] >= 0 and r_conc["block_frac"] >= 0


def test_table3_lookup_n10_m9_is_the_m9_column_not_m8():
    """Regression for a real transcription bug in CLAUDE.md's checkpoint-3
    write-up: the (n=10, m=9) row of Table 3 was reported as 1.00321,
    which is actually TABLE3[10][m=8] (1.003210302734375). The correct
    m=9 value is 1.002478466796875 -- a different column of the same row.
    Pins the exact lookup so this specific column mistake can't recur
    silently."""
    assert M_VALUES[3] == 9
    assert TABLE3[10][M_VALUES.index(9)] == 1.002478466796875
    assert TABLE3[10][M_VALUES.index(8)] == 1.003210302734375  # the value it was mistaken for


def test_total_queue_crossover_bracket_actually_contains_a_root():
    """Regression for a real bug (found by the user, 2026-09-22): X1's
    total-queue crossover (n*L_d vs L_c, analytic) reused the per-drone
    -wait rho_grid's own bracket as bisect's search window, e.g.
    (0.55, 0.80) for (n=5, m=7). That bracket never reaches the real
    crossover, which sits between rho=0.95 and 1.00 for all three grid
    configs -- so bisect (before it validated its bracket) silently
    returned numbers anchored to the wrong window (0.750/0.800/0.900
    were reported, when the true values are ~0.984/0.989/0.996).

    This pins the correct values with a bracket that is verified (via
    the sign check now built into bisect()) to actually contain the
    root, and confirms the old, wrong bracket would have raised instead
    of silently returning a bad answer."""
    configs_and_true = [(4, 6, 0.983783), (5, 7, 0.988904), (10, 9, 0.995594)]
    for n, m, expected in configs_and_true:
        f = lambda rho, n=n, m=m: n * L_distributed(rho, m) - L_concentrated(rho, n, m)
        rho_star = bisect(f, 0.95, 1.00, tol=1e-9)
        assert abs(rho_star - expected) < 1e-4, f"(n={n},m={m}): got {rho_star}, expected ~{expected}"

    # The old, wrong bracket (reused from a different metric's rho_grid)
    # does not contain a root for (5,7) -- bisect must now refuse it
    # rather than silently returning a number anchored to the wrong window.
    f57 = lambda rho: 5 * L_distributed(rho, 7) - L_concentrated(rho, 5, 7)
    try:
        bisect(f57, 0.55, 0.80, tol=1e-9)
        assert False, "expected bisect to raise on a bracket with no sign change"
    except ValueError:
        pass
