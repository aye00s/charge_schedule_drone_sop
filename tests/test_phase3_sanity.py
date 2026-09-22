import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase1_baseline import L_distributed, t_distributed
from sim.scheduler import simulate_regime

MU = 1.0
HORIZON = 50_000
SEEDS = [1, 2, 3, 4, 5]


def _rel_err(sim_v, analytic_v):
    return abs(sim_v - analytic_v) / max(abs(analytic_v), 1e-9)


def test_slack_zero_reduction_matches_phase2_analytics():
    """With slack=0 (deadline == arrival time) and fixed-split routing, R3's
    multi-station engine must degenerate to n independent M/M/1/m queues and
    reproduce the Phase 1/2 analytics -- this validates the new engine
    against the already-validated one, not just against theory."""
    n, m, rho = 5, 7, 1.0
    lam_total = rho * n * MU
    L_vals, t_vals = [], []
    for seed in SEEDS:
        r = simulate_regime(routing="fixed_split", order="fcfs", n_stations=n,
                             capacity=m, lam_total=lam_total, mu=MU,
                             horizon=HORIZON, seed=seed, slack_mean=0.0)
        L_vals.append(r["L"])
        t_vals.append(r["wait"] * lam_total)

    L_mean = np.mean(L_vals)
    t_mean = np.mean(t_vals)
    assert _rel_err(L_mean, L_distributed(rho, m)) < 0.10
    assert _rel_err(t_mean, t_distributed(rho, m, n)) < 0.10


def test_conservation_r2_matches_r1_on_averages():
    """H1 / Kleinrock's conservation law: reordering service by a priority
    that is independent of service duration (least-slack-first here) must
    not change average queue length or average wait, only per-drone
    outcomes. If this fails, there is a bug, not a modeling result."""
    n, m, rho = 5, 7, 0.9
    lam_total = rho * n * MU
    slack_mean = 1.0 / MU  # per the recorded open-decision default

    L_fcfs, t_fcfs, L_prio, t_prio = [], [], [], []
    for seed in SEEDS:
        r1 = simulate_regime(routing="fixed_split", order="fcfs", n_stations=n,
                              capacity=m, lam_total=lam_total, mu=MU,
                              horizon=HORIZON, seed=seed, slack_mean=slack_mean)
        r2 = simulate_regime(routing="fixed_split", order="priority", n_stations=n,
                              capacity=m, lam_total=lam_total, mu=MU,
                              horizon=HORIZON, seed=seed, slack_mean=slack_mean)
        L_fcfs.append(r1["L"]); t_fcfs.append(r1["wait"])
        L_prio.append(r2["L"]); t_prio.append(r2["wait"])

    L_fcfs_m, L_prio_m = np.mean(L_fcfs), np.mean(L_prio)
    t_fcfs_m, t_prio_m = np.mean(t_fcfs), np.mean(t_prio)

    assert _rel_err(L_prio_m, L_fcfs_m) < 0.10
    assert _rel_err(t_prio_m, t_fcfs_m) < 0.10


def test_priority_changes_per_drone_outcomes():
    """Complement to the conservation check: priority ordering must change
    *which* drones wait (per-drone outcomes differ), even though the
    averages above don't. This does NOT assert priority is better -- H2
    (Section 9) is a hypothesis to test empirically, not a built-in
    assumption. At (n=5, m=7, rho=0.9, slack_mean=1/mu), 10-seed runs showed
    priority *reduces* the within-window fraction by ~1.8pp, consistently
    (std 0.0004) -- plausibly EDF's known overload "domino effect" (serving
    doomed near-deadline jobs first at the expense of nearly-on-time ones)
    since slack here is tight relative to load. Reported as-is, not tuned
    away."""
    n, m, rho = 5, 7, 0.9
    lam_total = rho * n * MU
    slack_mean = 1.0 / MU

    r1 = simulate_regime(routing="fixed_split", order="fcfs", n_stations=n,
                          capacity=m, lam_total=lam_total, mu=MU,
                          horizon=HORIZON, seed=1, slack_mean=slack_mean)
    r2 = simulate_regime(routing="fixed_split", order="priority", n_stations=n,
                          capacity=m, lam_total=lam_total, mu=MU,
                          horizon=HORIZON, seed=1, slack_mean=slack_mean)
    assert r2["within_window"] != r1["within_window"]
