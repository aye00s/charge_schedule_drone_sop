"""REMEDIATION.md X8: weight sensitivity. Sweep w1/w2 (F11 priority
weights) and alpha/beta/gamma (F12 objective weights) on a small grid,
report how results change. Weights are NOT selected to favour any
hypothesis -- the grids below are symmetric around the project's existing
default (1,1) / (1,1,1), per the Section 7 answer already recorded in
CLAUDE.md Section 13.

Design:
- w1/w2 affect actual scheduling DECISIONS (F11's priority ranking), so
  each combination needs its own simulation run.
- alpha/beta/gamma affect ONLY how Z is computed from the three already-
  normalized terms (f12_cmax_term, f12_energy_term, f12_tardy_term) --
  confirmed directly from sim/mission_sim.py (alpha/beta/gamma feed
  objective_F12 at the very end, never a dispatch decision). So every
  alpha/beta/gamma combination is computed POST HOC from the SAME w1/w2
  runs, no extra simulation needed -- this also directly tests whether a
  different objective weighting would favour a different w1/w2 choice.
- 2 representative configs, reused from X3's own definitions
  (density_scarce and load_saturated -- the two configs with genuine
  contention/nonzero miss rates in X3, where weight choice could
  plausibly matter; every other X3 config saturates near 0 miss rate for
  every policy tested so far, leaving no signal for a sensitivity sweep).
- 15 (layout, seed) pairs per w1/w2 combination (a reduced-scope sweep,
  not full 30-pair rigor -- this is an exploratory sensitivity check per
  REMEDIATION.md's own wording, not a headline result).

Usage: `python experiments/x8_weight_sensitivity.py --pilot` for a small
timing check; no flag for the full run.
"""

import argparse
import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.x3_baselines_vs_ours import (DEADLINE_WINDOW_MIN, DRAIN_CAP_MIN, HORIZON_MIN, N_UAVS,
                                               station_layout)
from sim.mission_sim import run_mission_sim

CONFIGS = [
    ("density_scarce", 2, 0.8),
    ("load_saturated", 5, 1.6),
]

W_GRID = [(1.0, 1.0), (2.0, 1.0), (1.0, 2.0), (0.5, 0.5)]
OBJECTIVE_GRID = [(1.0, 1.0, 1.0), (2.0, 1.0, 1.0), (1.0, 2.0, 1.0), (1.0, 1.0, 2.0)]


def layout_seed_pairs(n_layouts=5, n_seeds_per_layout=3, base_seed_offset=0):
    pairs = []
    seed = 1 + base_seed_offset
    for layout_id in range(n_layouts):
        for _ in range(n_seeds_per_layout):
            pairs.append((layout_id, seed))
            seed += 1
    return pairs


def run_one(n_stations, mission_rate, layout_id, seed, w1, w2):
    stations = station_layout(n_stations, layout_seed=1000 + layout_id)
    r = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=2,
                         horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                         deadline_window_min=DEADLINE_WINDOW_MIN, drain_cap_min=DRAIN_CAP_MIN,
                         policy="ours", w1=w1, w2=w2)
    r["miss_rate"] = r["tardy_count"] / r["missions_total"] if r["missions_total"] > 0 else 0.0
    return r


def run_pilot():
    pairs = [(0, 1), (0, 2)]
    print(f"PILOT: config=density_scarce, pairs={pairs}, w1/w2 grid={W_GRID}\n")
    t0 = time.time()
    n_runs = 0
    for w1, w2 in W_GRID:
        for layout_id, seed in pairs:
            rt0 = time.time()
            r = run_one(2, 0.8, layout_id, seed, w1, w2)
            rt = time.time() - rt0
            n_runs += 1
            print(f"w1={w1} w2={w2} layout={layout_id} seed={seed} runtime={rt:.2f}s "
                  f"miss_rate={r['miss_rate']:.3f} f12_Z={r['f12_Z']:.4f}", flush=True)
    total_s = time.time() - t0
    print(f"\nPilot: {n_runs} runs in {total_s:.1f}s ({total_s/n_runs:.3f}s/run)")
    full_n_runs = len(CONFIGS) * len(W_GRID) * 15
    est_s = full_n_runs * (total_s / n_runs)
    print(f"Full X8: {len(CONFIGS)} configs x {len(W_GRID)} w-combos x 15 pairs = {full_n_runs} runs. "
          f"Estimated: {est_s/60:.1f} min ({est_s:.0f}s)")


def run_full():
    pairs = layout_seed_pairs(n_layouts=5, n_seeds_per_layout=3)
    assert len(pairs) == 15
    total_runs = len(CONFIGS) * len(W_GRID) * len(pairs)
    print(f"Full X8: {len(CONFIGS)} configs x {len(W_GRID)} w-combos x {len(pairs)} pairs = {total_runs} runs")
    t0 = time.time()
    all_rows = []
    for config_name, n_stations, mission_rate in CONFIGS:
        for w1, w2 in W_GRID:
            for layout_id, seed in pairs:
                r = run_one(n_stations, mission_rate, layout_id, seed, w1, w2)
                all_rows.append(dict(
                    config=config_name, w1=w1, w2=w2, layout_id=layout_id, seed=seed,
                    miss_rate=r["miss_rate"], unfinished_at_cap=r["unfinished_at_cap"],
                    f12_cmax_term=r["f12_cmax_term"], f12_energy_term=r["f12_energy_term"],
                    f12_tardy_term=r["f12_tardy_term"], safety_violations=r["safety_violations"],
                ))
        print(f"  config={config_name} done, elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x8_weight_sensitivity_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    print("\n=== w1/w2 sensitivity: miss_rate and F12 terms (mean of 15 pairs) ===")
    for config_name, _, _ in CONFIGS:
        print(f"\n{config_name}:")
        for w1, w2 in W_GRID:
            rows = [r for r in all_rows if r["config"] == config_name and r["w1"] == w1 and r["w2"] == w2]
            miss = np.mean([r["miss_rate"] for r in rows])
            unfin = np.mean([r["unfinished_at_cap"] for r in rows])
            cmax_t = np.mean([r["f12_cmax_term"] for r in rows])
            energy_t = np.mean([r["f12_energy_term"] for r in rows])
            tardy_t = np.mean([r["f12_tardy_term"] for r in rows])
            print(f"  w1={w1:.1f} w2={w2:.1f}  miss_rate={miss:.4f}  unfinished={unfin:.2f}  "
                  f"cmax_term={cmax_t:.4f}  energy_term={energy_t:.4f}  tardy_term={tardy_t:.4f}")

    print("\n=== alpha/beta/gamma sensitivity: Z under each objective weighting, per w1/w2 "
          "(computed post-hoc from the SAME runs -- tests whether a different objective "
          "weighting would favour a different w1/w2 choice) ===")
    for config_name, _, _ in CONFIGS:
        print(f"\n{config_name}:")
        for alpha, beta, gamma in OBJECTIVE_GRID:
            print(f"  alpha={alpha:.1f} beta={beta:.1f} gamma={gamma:.1f}:")
            best_w, best_z = None, None
            for w1, w2 in W_GRID:
                rows = [r for r in all_rows if r["config"] == config_name and r["w1"] == w1 and r["w2"] == w2]
                z_vals = [alpha * r["f12_cmax_term"] + beta * r["f12_energy_term"] + gamma * r["f12_tardy_term"]
                          for r in rows]
                mean_z = np.mean(z_vals)
                print(f"    w1={w1:.1f} w2={w2:.1f}  mean Z={mean_z:.4f}")
                if best_z is None or mean_z < best_z:
                    best_z, best_w = mean_z, (w1, w2)
            print(f"    -> best w1/w2 under this weighting: {best_w} (Z={best_z:.4f})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.pilot:
        run_pilot()
    else:
        run_full()
