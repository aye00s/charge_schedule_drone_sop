"""Narrows the "reservation-based deterministic scheduling" attribution
from the X4 follow-up (2026-09-23, per user instruction): B3 vs baseline
still differs in reservations (F9), routing (nearest-station within F5's
gate either way, but B3 additionally has F7's deterministic wait/F9
reservation queue), AND priority (F10/F11) all at once, so "reservation-
based scheduling" was not yet isolated from "priority-based mission
assignment." Runs B3 with use_reservation=False and B3 with
use_priority=False across the identical X4 grid (2 layout arms x 7 load
points x 30 pairs = 420 runs each), so each component's own contribution
can be read off directly against the already-recorded B3 and baseline
numbers.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.x4_layout_crossover import (DEADLINE_WINDOW_MIN, DRAIN_CAP_MIN, HORIZON_MIN,
                                              LOAD_POINTS, N_UAVS, TOTAL_PADS, centroid,
                                              distributed_layout, layout_seed_pairs)
from sim.mission_sim import run_mission_sim

VARIANTS = [
    ("B3_no_reservation", dict(policy="ours", use_queue_term=False, use_reservation=False)),
    ("B3_no_priority", dict(policy="ours", use_queue_term=False, use_priority=False)),
]


def run_one(policy_kwargs, layout_arm, layout_id, mission_rate, seed):
    dist_stations = distributed_layout(layout_id)
    if layout_arm == "distributed":
        stations, pads_per_station = dist_stations, 1
    else:
        stations, pads_per_station = [centroid(dist_stations)], TOTAL_PADS
    r = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=pads_per_station,
                         horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                         deadline_window_min=DEADLINE_WINDOW_MIN, drain_cap_min=DRAIN_CAP_MIN,
                         **policy_kwargs)
    delays = [cs["total_delay_min"] for cs in r["session_log"] if cs.get("total_delay_min") is not None]
    r["mean_charge_delay_min"] = float(np.mean(delays)) if delays else 0.0
    r["miss_rate"] = r["tardy_count"] / r["missions_total"] if r["missions_total"] > 0 else 0.0
    return r


def main():
    pairs = layout_seed_pairs()
    total_runs = len(VARIANTS) * 2 * len(LOAD_POINTS) * len(pairs)
    print(f"B3 attribution variants: {len(VARIANTS)} variants x 2 layouts x {len(LOAD_POINTS)} "
          f"load points x {len(pairs)} pairs = {total_runs} runs")
    t0 = time.time()
    all_rows = []
    for variant_name, kwargs in VARIANTS:
        for mission_rate in LOAD_POINTS:
            for arm in ("concentrated", "distributed"):
                for layout_id, seed in pairs:
                    r = run_one(kwargs, arm, layout_id, mission_rate, seed)
                    all_rows.append(dict(
                        mission_rate=mission_rate, arm=arm, policy=variant_name, layout_id=layout_id, seed=seed,
                        missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                        unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                        mean_charge_delay_min=r["mean_charge_delay_min"],
                        f12_Z=r["f12_Z"], safety_violations=r["safety_violations"],
                        charge_sessions=r["charge_sessions"],
                    ))
            print(f"  variant={variant_name} rate={mission_rate} arm={arm} done, "
                  f"elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x4_b3_attribution_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    print("\n=== Crossover summary, both attribution variants (mean across 30 pairs per point) ===")
    for variant_name, _ in VARIANTS:
        print(f"\n{variant_name}:")
        for mission_rate in LOAD_POINTS:
            c_rows = [r for r in all_rows if r["policy"] == variant_name and r["arm"] == "concentrated"
                      and r["mission_rate"] == mission_rate]
            d_rows = [r for r in all_rows if r["policy"] == variant_name and r["arm"] == "distributed"
                      and r["mission_rate"] == mission_rate]
            c_delay = np.mean([r["mean_charge_delay_min"] for r in c_rows])
            d_delay = np.mean([r["mean_charge_delay_min"] for r in d_rows])
            c_miss = np.mean([r["miss_rate"] for r in c_rows])
            d_miss = np.mean([r["miss_rate"] for r in d_rows])
            c_unfin = np.mean([r["unfinished_at_cap"] for r in c_rows])
            d_unfin = np.mean([r["unfinished_at_cap"] for r in d_rows])
            winner = "concentrated" if c_delay < d_delay else "distributed"
            print(f"  rate={mission_rate:.1f}  delay: conc={c_delay:7.2f} dist={d_delay:7.2f} -> {winner:12s}  "
                  f"miss: conc={c_miss:.3f} dist={d_miss:.3f}  unfin: conc={c_unfin:.1f} dist={d_unfin:.1f}")


if __name__ == "__main__":
    main()
