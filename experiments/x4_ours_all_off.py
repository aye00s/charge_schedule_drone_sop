"""Follow-up to the B3 attribution check (2026-09-23, per user instruction):
removing reservation (F9), priority (F10/F11), or partial charging
individually from B3 each left the distributed-wins pattern unchanged, but
`baseline` -- which is ALSO nearest-station routing with no reservation, no
priority, and full charging -- does NOT reproduce it (catastrophic backlog
instead). So "nearest-station routing" alone, as `baseline` embodies it,
is already known not to be the driver from the existing X4 data.

This script tests the remaining candidate precisely: run `ours` with ALL
SIX ablation flags off simultaneously (use_queue_term=False,
use_reservation=False, use_priority=False, use_partial=False,
use_jit=False, use_charge_time_term=False) across the identical X4 grid.
This isolates whether it's the `ours`/B3 ENGINE's structural dispatch
mechanism (F5's gate-based proactive charging trigger + F8's argmin
routing, neither gated by any flag) that drives the result, as opposed to
`baseline`'s reactive SoC-threshold trigger -- rather than any combination
of the six flags themselves.
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

VARIANT_NAME = "ours_all_off"
VARIANT_KWARGS = dict(policy="ours", use_queue_term=False, use_reservation=False,
                       use_priority=False, use_partial=False, use_jit=False,
                       use_charge_time_term=False)


def run_one(layout_arm, layout_id, mission_rate, seed):
    dist_stations = distributed_layout(layout_id)
    if layout_arm == "distributed":
        stations, pads_per_station = dist_stations, 1
    else:
        stations, pads_per_station = [centroid(dist_stations)], TOTAL_PADS
    r = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=pads_per_station,
                         horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                         deadline_window_min=DEADLINE_WINDOW_MIN, drain_cap_min=DRAIN_CAP_MIN,
                         **VARIANT_KWARGS)
    delays = [cs["total_delay_min"] for cs in r["session_log"] if cs.get("total_delay_min") is not None]
    r["mean_charge_delay_min"] = float(np.mean(delays)) if delays else 0.0
    r["miss_rate"] = r["tardy_count"] / r["missions_total"] if r["missions_total"] > 0 else 0.0
    return r


def main():
    pairs = layout_seed_pairs()
    total_runs = 2 * len(LOAD_POINTS) * len(pairs)
    print(f"ours_all_off routing-isolation check: 2 arms x {len(LOAD_POINTS)} load points x "
          f"{len(pairs)} pairs = {total_runs} runs")
    t0 = time.time()
    all_rows = []
    for mission_rate in LOAD_POINTS:
        for arm in ("concentrated", "distributed"):
            for layout_id, seed in pairs:
                r = run_one(arm, layout_id, mission_rate, seed)
                all_rows.append(dict(
                    mission_rate=mission_rate, arm=arm, policy=VARIANT_NAME, layout_id=layout_id, seed=seed,
                    missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                    unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                    mean_charge_delay_min=r["mean_charge_delay_min"],
                    f12_Z=r["f12_Z"], safety_violations=r["safety_violations"],
                    charge_sessions=r["charge_sessions"],
                ))
            print(f"  rate={mission_rate} arm={arm} done, elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x4_ours_all_off_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    print("\n=== ours_all_off crossover summary (mean across 30 pairs per point) ===")
    for mission_rate in LOAD_POINTS:
        c_rows = [r for r in all_rows if r["arm"] == "concentrated" and r["mission_rate"] == mission_rate]
        d_rows = [r for r in all_rows if r["arm"] == "distributed" and r["mission_rate"] == mission_rate]
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
