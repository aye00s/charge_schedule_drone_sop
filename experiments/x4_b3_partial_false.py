"""Follow-up to experiments/x4_layout_crossover.py (2026-09-23, per user
instruction): the original X4 write-up said "partial charging is what
makes distributed efficient," inferred from B3 (use_queue_term=False,
use_partial=True, still using F9 reservations and F10/F11 priority) vs.
baseline/jsq (no reservations, no priority, no partial charging) -- but
B3 differs from baseline/jsq on routing, priority AND reservations, not
just partial charging, so that claim was never actually isolated. This
runs a `B3 + use_partial=False` variant (full charge every time, still
nearest-station routing / F9 reservations / F10-F11 priority, i.e. B3
with the ONE remaining difference from full-charge removed) across the
identical X4 grid, so partial charging's own contribution can be read
off directly: B3_partial_False vs B3 isolates use_partial; B3_partial_False
vs baseline still differs on routing/priority/reservations, so it does not
fully collapse to baseline, but it does show whether use_partial is
doing any of the work B3 vs baseline/jsq showed.
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

VARIANT_NAME = "B3_partial_False"
VARIANT_KWARGS = dict(policy="ours", use_queue_term=False, use_partial=False)


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
    r["p95_charge_delay_min"] = float(np.percentile(delays, 95)) if delays else 0.0
    r["miss_rate"] = r["tardy_count"] / r["missions_total"] if r["missions_total"] > 0 else 0.0
    return r


def main():
    pairs = layout_seed_pairs()
    assert len(pairs) == 30
    total_runs = 2 * len(LOAD_POINTS) * len(pairs)
    print(f"X4 B3_partial_False re-run: 2 layouts x {len(LOAD_POINTS)} load points x "
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
                    p95_charge_delay_min=r["p95_charge_delay_min"],
                    f12_Z=r["f12_Z"], f12_cmax_term=r["f12_cmax_term"],
                    f12_energy_term=r["f12_energy_term"], f12_tardy_term=r["f12_tardy_term"],
                    safety_violations=r["safety_violations"], gate_binding_rate=r["gate_binding_rate"],
                    mean_on_pad_queue_length=r["mean_on_pad_queue_length"],
                    charge_sessions=r["charge_sessions"],
                ))
        print(f"  rate={mission_rate} done, elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x4_b3_partial_false_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    print(f"\n=== {VARIANT_NAME} crossover summary (mean across 30 pairs per point) ===")
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
