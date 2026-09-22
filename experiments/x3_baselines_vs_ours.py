"""REMEDIATION.md X3: our method vs baselines, the paper's main comparison.
Phase 4 mission simulator, same (layout, seed) pairs for every policy (CRN).

Design decisions recorded here (see CLAUDE.md Section 13's X3 pre-
registration for the primary/secondary metric split, declared before this
script was run):
- 9 policies: baseline (B1/B2), jsq (B4), ours (defaults, JIT off),
  and the 6 single-flag ablations -- use_queue_term=False IS B3,
  use_jit=True IS the recorded "ours+JIT" named variant, so neither needs
  a separate run.
- 5 configs: 3 station-density levels (scarce=2, balanced=5, abundant=10
  stations, pads_per_station=2 fixed -- following Phase 6's own precedent
  of varying station COUNT, not pads/station) at nominal load, and 3
  mission-load levels (light=0.3, nominal=0.8, saturated=1.6/min) at
  balanced density, sharing the (balanced, nominal) point once. Not a
  full 3x3 grid, to keep runtime tractable for a first pass.
- Per config: 5 random station layouts x 6 seeds = 30 (layout, seed)
  pairs, every policy run on the same 30 pairs.
- drain_cap_min = 3 * deadline_window_min = 135min, so F12's C_max/sum(T_k)
  mean something even under saturated load where not everything finishes
  by the horizon; unfinished_at_cap reported for every run.
- n_uavs=20, horizon_min=1000, deadline_window_min=45 (project defaults).

Usage: `python experiments/x3_baselines_vs_ours.py --pilot` for a small
timing/correctness check (1 config, 1 layout, 2 seeds); no flag for the
full run.
"""

import argparse
import csv
import datetime
import itertools
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.mission_sim import run_mission_sim

N_UAVS = 20
HORIZON_MIN = 1000.0
DEADLINE_WINDOW_MIN = 45.0
DRAIN_CAP_MIN = 3 * DEADLINE_WINDOW_MIN
AREA_SIDE_M = 2000.0

DENSITY_STATIONS = {"scarce": 2, "balanced": 5, "abundant": 10}
LOAD_RATES = {"light": 0.3, "nominal": 0.8, "saturated": 1.6}

# 5 configs: (config_name, n_stations, mission_rate)
CONFIGS = [
    ("density_scarce", DENSITY_STATIONS["scarce"], LOAD_RATES["nominal"]),
    ("density_balanced_nominal_load", DENSITY_STATIONS["balanced"], LOAD_RATES["nominal"]),
    ("density_abundant", DENSITY_STATIONS["abundant"], LOAD_RATES["nominal"]),
    ("load_light", DENSITY_STATIONS["balanced"], LOAD_RATES["light"]),
    ("load_saturated", DENSITY_STATIONS["balanced"], LOAD_RATES["saturated"]),
]

POLICIES = [
    ("baseline", dict(policy="baseline")),
    ("jsq", dict(policy="jsq")),
    ("ours", dict(policy="ours")),
    ("B3_use_queue_term_False", dict(policy="ours", use_queue_term=False)),
    ("use_reservation_False", dict(policy="ours", use_reservation=False)),
    ("use_priority_False", dict(policy="ours", use_priority=False)),
    ("use_partial_False", dict(policy="ours", use_partial=False)),
    ("ours_JIT", dict(policy="ours", use_jit=True)),
    ("use_charge_time_term_False", dict(policy="ours", use_charge_time_term=False)),
]

# Primary comparisons for the pre-registered analysis (CLAUDE.md Section 13)
PRIMARY_COMPARISONS = [
    ("ours", "baseline"),
    ("ours", "jsq"),
    ("ours", "B3_use_queue_term_False"),
]
PRIMARY_METRICS = ["f12_Z", "miss_rate"]


def station_layout(n_stations, layout_seed):
    rng = np.random.default_rng(layout_seed)
    return [tuple(rng.uniform(0, AREA_SIDE_M, size=2)) for _ in range(n_stations)]


def layout_seed_pairs(n_layouts, n_seeds_per_layout, base_seed_offset=0):
    """5 layouts x 6 seeds = 30 (layout_id, seed) pairs. Seeds are distinct
    across the whole grid (not reused per layout) so every one of the 30
    runs per policy uses an independently-drawn mission stream, while every
    POLICY sees the identical 30 pairs (CRN)."""
    pairs = []
    seed = 1 + base_seed_offset
    for layout_id in range(n_layouts):
        for _ in range(n_seeds_per_layout):
            pairs.append((layout_id, seed))
            seed += 1
    return pairs


def run_one(policy_kwargs, n_stations, mission_rate, layout_id, seed):
    stations = station_layout(n_stations, layout_seed=1000 + layout_id)
    r = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=2,
                         horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                         deadline_window_min=DEADLINE_WINDOW_MIN, drain_cap_min=DRAIN_CAP_MIN,
                         **policy_kwargs)
    r["miss_rate"] = r["tardy_count"] / r["missions_total"] if r["missions_total"] > 0 else 0.0
    return r


def run_pilot():
    """1 config (balanced density, nominal load), 1 layout, 2 seeds, every
    policy -- timing/correctness check only, not a result."""
    config_name, n_stations, mission_rate = CONFIGS[1]
    pairs = [(0, 1), (0, 2)]
    print(f"PILOT: config={config_name} n_stations={n_stations} mission_rate={mission_rate} "
          f"pairs={pairs}\n")
    t0 = time.time()
    rows = []
    for policy_name, kwargs in POLICIES:
        for layout_id, seed in pairs:
            rt0 = time.time()
            r = run_one(kwargs, n_stations, mission_rate, layout_id, seed)
            rt = time.time() - rt0
            rows.append(dict(policy=policy_name, layout_id=layout_id, seed=seed, runtime_s=rt,
                              missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                              unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                              f12_Z=r["f12_Z"], f12_cmax_term=r["f12_cmax_term"],
                              f12_energy_term=r["f12_energy_term"], f12_tardy_term=r["f12_tardy_term"],
                              safety_violations=r["safety_violations"], gate_binding_rate=r["gate_binding_rate"],
                              mean_on_pad_queue_length=r["mean_on_pad_queue_length"],
                              runtime_per_decision_us=r["runtime_per_decision_us"]))
            print(f"{policy_name:28s} layout={layout_id} seed={seed} runtime={rt:.3f}s "
                  f"completed={r['missions_completed']}/{r['missions_total']} unfin={r['unfinished_at_cap']} "
                  f"miss_rate={r['miss_rate']:.3f} Z={r['f12_Z']:.4f} safety={r['safety_violations']} "
                  f"gate_bind={r['gate_binding_rate']:.3f} queue_len={r['mean_on_pad_queue_length']:.3f} "
                  f"rt/decision={r['runtime_per_decision_us']:.1f}us", flush=True)
    total_s = time.time() - t0
    n_runs = len(rows)
    print(f"\nPilot: {n_runs} runs in {total_s:.1f}s ({total_s/n_runs:.3f}s/run average)")

    full_n_runs = len(POLICIES) * len(CONFIGS) * 30
    est_s = full_n_runs * (total_s / n_runs)
    print(f"Full X3: {len(POLICIES)} policies x {len(CONFIGS)} configs x 30 (layout,seed) pairs "
          f"= {full_n_runs} runs. Estimated at pilot's per-run rate: {est_s/60:.1f} min "
          f"({est_s:.0f}s)")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x3_pilot_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {n_runs} rows to {out_path}")


def holm_correct(pvals):
    """Holm-Bonferroni step-down correction. Returns adjusted p-values in
    the ORIGINAL order of `pvals`."""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    adjusted = [None] * n
    running_max = 0.0
    for rank, idx in enumerate(order):
        adj = (n - rank) * pvals[idx]
        running_max = max(running_max, adj)
        adjusted[idx] = min(1.0, running_max)
    return adjusted


def run_full():
    pairs = layout_seed_pairs(n_layouts=5, n_seeds_per_layout=6)
    assert len(pairs) == 30
    print(f"Full X3: {len(POLICIES)} policies x {len(CONFIGS)} configs x {len(pairs)} "
          f"(layout,seed) pairs = {len(POLICIES)*len(CONFIGS)*len(pairs)} runs")
    t0 = time.time()
    all_rows = []
    for config_name, n_stations, mission_rate in CONFIGS:
        for policy_name, kwargs in POLICIES:
            for layout_id, seed in pairs:
                r = run_one(kwargs, n_stations, mission_rate, layout_id, seed)
                all_rows.append(dict(
                    config=config_name, policy=policy_name, layout_id=layout_id, seed=seed,
                    n_stations=n_stations, mission_rate=mission_rate,
                    missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                    unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                    f12_Z=r["f12_Z"], f12_cmax_term=r["f12_cmax_term"],
                    f12_energy_term=r["f12_energy_term"], f12_tardy_term=r["f12_tardy_term"],
                    f12_makespan_capped_min=r["f12_makespan_capped_min"],
                    f12_tardiness_capped_min=r["f12_tardiness_capped_min"],
                    makespan_min=r["makespan_min"], total_tardiness_min=r["total_tardiness_min"],
                    mean_charge_duration_min=r["mean_charge_duration_min"],
                    total_charge_energy_wh=r["total_charge_energy_wh"],
                    mission_flight_energy_wh=r["mission_flight_energy_wh"],
                    safety_violations=r["safety_violations"], gate_binding_rate=r["gate_binding_rate"],
                    mean_on_pad_queue_length=r["mean_on_pad_queue_length"],
                    runtime_per_decision_us=r["runtime_per_decision_us"],
                    charge_sessions=r["charge_sessions"],
                ))
        print(f"  config={config_name} done, elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x3_full_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    # Pre-registered primary analysis: paired Wilcoxon per config, per
    # comparison, per primary metric; Holm-corrected within each config's
    # family of len(PRIMARY_COMPARISONS)*len(PRIMARY_METRICS) tests.
    print("\n=== Primary analysis (pre-registered, Holm-corrected within each config's 6 tests) ===")
    for config_name, _, _ in CONFIGS:
        cfg_rows = [row for row in all_rows if row["config"] == config_name]
        by_policy = {p: {(row["layout_id"], row["seed"]): row for row in cfg_rows if row["policy"] == p}
                     for p, _ in POLICIES}
        pvals, labels = [], []
        for a, b in PRIMARY_COMPARISONS:
            for metric in PRIMARY_METRICS:
                common_keys = sorted(set(by_policy[a]) & set(by_policy[b]))
                da = [by_policy[a][k][metric] for k in common_keys]
                db = [by_policy[b][k][metric] for k in common_keys]
                diff = [x - y for x, y in zip(da, db)]
                if all(d == 0 for d in diff):
                    p = 1.0
                else:
                    _, p = wilcoxon(da, db)
                pvals.append(p)
                labels.append(f"{a} vs {b}, {metric}")
        adj = holm_correct(pvals)
        print(f"\n{config_name}:")
        for label, p, a in zip(labels, pvals, adj):
            print(f"  {label:45s} raw p={p:.4g}  Holm-adjusted p={a:.4g}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.pilot:
        run_pilot()
    else:
        run_full()
