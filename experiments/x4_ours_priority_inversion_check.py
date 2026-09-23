"""Follow-up to X4 (2026-09-23, per user instruction): at the loads where
concentrated overtakes distributed for `ours` (rate=1.1, 1.3, 1.6 -- see
CLAUDE.md Section 13's X4 report), check whether the SAME priority-
inversion mechanism X3 root-caused in density_scarce is responsible here
too. For each missed mission (late or unfinished) on the distributed arm,
report the drone's priority at reservation time and how many lower-
priority reservations sat ahead of it at its pad -- the same diagnostic
run for X3, same fields (priority, ahead_lower_priority, ahead_total,
already logged on every 'ours' session by sim/mission_sim.py).

All 30 (layout, seed) pairs, matching X4's own resolution (cheap at this
scale: ~90 runs total).
"""

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.x4_layout_crossover import (DEADLINE_WINDOW_MIN, DRAIN_CAP_MIN, HORIZON_MIN,
                                              N_UAVS, distributed_layout, layout_seed_pairs)
from sim.mission_sim import run_mission_sim

RATES = [1.1, 1.3, 1.6]


def main():
    pairs = layout_seed_pairs()
    for rate in RATES:
        print(f"\n=== rate={rate}, distributed arm, 'ours' (default F9), all 30 pairs ===")
        linked = []
        ahead_counts_all = []
        for layout_id, seed in pairs:
            stations = distributed_layout(layout_id)
            r = run_mission_sim(policy="ours", n_uavs=N_UAVS, station_positions=stations,
                                 pads_per_station=1, horizon_min=HORIZON_MIN, seed=seed,
                                 mission_rate_per_min=rate, deadline_window_min=DEADLINE_WINDOW_MIN,
                                 drain_cap_min=DRAIN_CAP_MIN)
            sessions = r["session_log"]
            ahead_counts_all.extend(cs["ahead_lower_priority"] for cs in sessions)

            assigned = r["mission_assigned_uav"]
            releases = r["mission_release_times"]
            completed_times = r["mission_completed_times"]
            deadlines = r["mission_deadlines"]
            per_uav_missions = defaultdict(list)
            for a, rel, ct, dl in zip(assigned, releases, completed_times, deadlines):
                if a is not None:
                    per_uav_missions[a].append((rel, ct, dl))
            for u in per_uav_missions:
                per_uav_missions[u].sort()

            for cs in sessions:
                completion_t = cs["realised_start"] + cs["duration_min"]
                u = cs["uav"]
                cands = [(rel, ct, dl) for (rel, ct, dl) in per_uav_missions.get(u, []) if rel >= completion_t]
                if cands:
                    rel, ct, dl = cands[0]
                    bad = (ct is None) or (ct > dl)
                    linked.append((cs["ahead_lower_priority"], bad))

        n_sessions = len(ahead_counts_all)
        inv_frac = np.mean([a > 0 for a in ahead_counts_all])
        print(f"total sessions={n_sessions}  fraction with ahead_lower_priority>0 = {inv_frac:.4f}  "
              f"mean ahead_lower_priority = {np.mean(ahead_counts_all):.3f}")

        buckets = defaultdict(list)
        for ahead, bad in linked:
            key = ahead if ahead < 4 else "4+"
            buckets[key].append(bad)
        print(f"sessions linked to a next mission = {len(linked)}")
        print("ahead_lower_priority -> n, bad_fraction")
        for k in sorted(buckets, key=lambda x: (isinstance(x, str), x)):
            v = buckets[k]
            print(f"  {k}: n={len(v)}  bad_fraction={np.mean(v):.4f}")


if __name__ == "__main__":
    main()
