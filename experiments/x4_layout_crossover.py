"""REMEDIATION.md X4: layout crossover in the mission model -- the research
question end-to-end. Same total number of pads in two layouts: one hub
with n pads vs n stations with 1 pad each (spread over the area). Sweep
load; for each policy, find the load at which the better layout switches,
using per-drone charging delay and miss rate.

Design decisions (narrowed from X3's per user instruction, 2026-09-23):
- 4 policies only: baseline (B1/B2), jsq (B4), ours (defaults, JIT off),
  B3 (use_queue_term=False) -- the pre-registered primary comparisons,
  not the full 9-policy ablation set. Current (default) F9 behaviour is
  used throughout -- X3's result and this project's priority-inversion
  finding are noted as an important caveat on `ours`'s numbers here, not
  re-litigated with the new F9 variants in this run.
- 2 layouts, same total pad count (10): 'concentrated' = 1 station x 10
  pads; 'distributed' = 10 stations x 1 pad each, spread over the area.
  The distributed station positions are the SAME 5 random layouts X3
  used (layout_seed=1000+layout_id, n_stations=10 -- matches X3's
  "abundant" density layouts exactly), so results are comparable; the
  concentrated hub is placed at each distributed layout's centroid
  (same convention as E4(d) in the queue-only model).
- Load sweep: 7 points (0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.6 /min), finer
  than X3's 3 buckets since the crossover itself is the target here.
- 5 layouts x 6 seeds = 30 (layout, seed) pairs, same as X3, every
  policy on the same pairs.
- Metrics: per-drone charging delay (mean, p95) and miss rate (the
  crossover-defining metrics per REMEDIATION.md's own wording), F12 Z
  secondary.
- n_uavs=20, horizon=1000min, drain_cap_min=135 (3x deadline_window),
  matching X3.

Usage: `python experiments/x4_layout_crossover.py --pilot` for a small
timing/correctness check (1 load point, 2 seeds); no flag for the full
run.
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

from sim.mission_sim import run_mission_sim

N_UAVS = 20
HORIZON_MIN = 1000.0
DEADLINE_WINDOW_MIN = 45.0
DRAIN_CAP_MIN = 3 * DEADLINE_WINDOW_MIN
AREA_SIDE_M = 2000.0
TOTAL_PADS = 10

LOAD_POINTS = [0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.6]

POLICIES = [
    ("baseline", dict(policy="baseline")),
    ("jsq", dict(policy="jsq")),
    ("ours", dict(policy="ours")),
    ("B3_use_queue_term_False", dict(policy="ours", use_queue_term=False)),
]


def distributed_layout(layout_id):
    rng = np.random.default_rng(1000 + layout_id)  # same seed convention as X3
    return [tuple(rng.uniform(0, AREA_SIDE_M, size=2)) for _ in range(TOTAL_PADS)]


def centroid(positions):
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def layout_seed_pairs(n_layouts=5, n_seeds_per_layout=6):
    pairs = []
    seed = 1
    for layout_id in range(n_layouts):
        for _ in range(n_seeds_per_layout):
            pairs.append((layout_id, seed))
            seed += 1
    return pairs


def run_one(policy_kwargs, layout_arm, layout_id, mission_rate, seed):
    dist_stations = distributed_layout(layout_id)
    if layout_arm == "distributed":
        stations, pads_per_station = dist_stations, 1
    else:  # concentrated
        stations, pads_per_station = [centroid(dist_stations)], TOTAL_PADS
    r = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=pads_per_station,
                         horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                         deadline_window_min=DEADLINE_WINDOW_MIN, drain_cap_min=DRAIN_CAP_MIN,
                         **policy_kwargs)
    delays = [cs["total_delay_min"] for cs in r["session_log"] if cs.get("total_delay_min") is not None]
    r["mean_charge_delay_min"] = float(np.mean(delays)) if delays else 0.0
    r["p95_charge_delay_min"] = float(np.percentile(delays, 95)) if delays else 0.0
    r["miss_rate"] = r["tardy_count"] / r["missions_total"] if r["missions_total"] > 0 else 0.0
    return r


def run_pilot():
    pairs = [(0, 1), (0, 2)]
    mission_rate = LOAD_POINTS[3]  # 0.9, a middle point
    print(f"PILOT: mission_rate={mission_rate}, pairs={pairs}\n")
    t0 = time.time()
    rows = []
    for policy_name, kwargs in POLICIES:
        for arm in ("concentrated", "distributed"):
            for layout_id, seed in pairs:
                rt0 = time.time()
                r = run_one(kwargs, arm, layout_id, mission_rate, seed)
                rt = time.time() - rt0
                rows.append(dict(policy=policy_name, arm=arm, layout_id=layout_id, seed=seed, runtime_s=rt,
                                  missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                                  unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                                  mean_charge_delay_min=r["mean_charge_delay_min"],
                                  p95_charge_delay_min=r["p95_charge_delay_min"], f12_Z=r["f12_Z"],
                                  safety_violations=r["safety_violations"]))
                print(f"{policy_name:28s} {arm:13s} layout={layout_id} seed={seed} runtime={rt:.3f}s "
                      f"completed={r['missions_completed']}/{r['missions_total']} unfin={r['unfinished_at_cap']} "
                      f"miss_rate={r['miss_rate']:.3f} mean_delay={r['mean_charge_delay_min']:.2f} "
                      f"p95_delay={r['p95_charge_delay_min']:.2f} Z={r['f12_Z']:.4f} "
                      f"safety={r['safety_violations']}", flush=True)
    total_s = time.time() - t0
    n_runs = len(rows)
    print(f"\nPilot: {n_runs} runs in {total_s:.1f}s ({total_s/n_runs:.3f}s/run average)")
    full_n_runs = len(POLICIES) * 2 * len(LOAD_POINTS) * 30
    est_s = full_n_runs * (total_s / n_runs)
    print(f"Full X4: {len(POLICIES)} policies x 2 layouts x {len(LOAD_POINTS)} load points x 30 pairs "
          f"= {full_n_runs} runs. Estimated: {est_s/60:.1f} min ({est_s:.0f}s)")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x4_pilot_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {n_runs} rows to {out_path}")


def run_full():
    pairs = layout_seed_pairs()
    assert len(pairs) == 30
    total_runs = len(POLICIES) * 2 * len(LOAD_POINTS) * len(pairs)
    print(f"Full X4: {len(POLICIES)} policies x 2 layouts x {len(LOAD_POINTS)} load points x "
          f"{len(pairs)} pairs = {total_runs} runs")
    t0 = time.time()
    all_rows = []
    for mission_rate in LOAD_POINTS:
        for arm in ("concentrated", "distributed"):
            for policy_name, kwargs in POLICIES:
                for layout_id, seed in pairs:
                    r = run_one(kwargs, arm, layout_id, mission_rate, seed)
                    all_rows.append(dict(
                        mission_rate=mission_rate, arm=arm, policy=policy_name, layout_id=layout_id, seed=seed,
                        missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                        unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                        mean_charge_delay_min=r["mean_charge_delay_min"],
                        p95_charge_delay_min=r["p95_charge_delay_min"],
                        f12_Z=r["f12_Z"], f12_cmax_term=r["f12_cmax_term"],
                        f12_energy_term=r["f12_energy_term"], f12_tardy_term=r["f12_tardy_term"],
                        safety_violations=r["safety_violations"], gate_binding_rate=r["gate_binding_rate"],
                        mean_on_pad_queue_length=r["mean_on_pad_queue_length"],
                        charge_sessions=r["charge_sessions"],
                    ))
            print(f"  rate={mission_rate} arm={arm} done, elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x4_full_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    # Crossover summary: for each policy, at each load, which arm wins on
    # mean charge delay and on miss rate.
    print("\n=== Crossover summary (mean across 30 pairs per point) ===")
    for policy_name, _ in POLICIES:
        print(f"\n{policy_name}:")
        for mission_rate in LOAD_POINTS:
            c_rows = [r for r in all_rows if r["policy"] == policy_name and r["arm"] == "concentrated"
                      and r["mission_rate"] == mission_rate]
            d_rows = [r for r in all_rows if r["policy"] == policy_name and r["arm"] == "distributed"
                      and r["mission_rate"] == mission_rate]
            c_delay = np.mean([r["mean_charge_delay_min"] for r in c_rows])
            d_delay = np.mean([r["mean_charge_delay_min"] for r in d_rows])
            c_miss = np.mean([r["miss_rate"] for r in c_rows])
            d_miss = np.mean([r["miss_rate"] for r in d_rows])
            winner_delay = "concentrated" if c_delay < d_delay else "distributed"
            winner_miss = "concentrated" if c_miss < d_miss else ("distributed" if d_miss < c_miss else "tie")
            print(f"  rate={mission_rate:.1f}  delay: conc={c_delay:7.2f} dist={d_delay:7.2f} -> {winner_delay:12s}  "
                  f"miss: conc={c_miss:.3f} dist={d_miss:.3f} -> {winner_miss}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.pilot:
        run_pilot()
    else:
        run_full()
