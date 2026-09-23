"""Sanity check (2026-09-23, per user instruction): B3's flat ~1.01min
charge delay across the ENTIRE X4 load range (0.3-1.6/min) is only
meaningful if B3 is completing the same amount of work as baseline, not
quietly doing less. Distributed arm only (that's the value being
checked), all 7 load points, all 30 pairs, for baseline and B3 --
reports completed-mission count, station utilisation (total charging
time / (horizon * total pads)), and mean charging sessions per drone,
side by side.
"""

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.x4_layout_crossover import (DEADLINE_WINDOW_MIN, DRAIN_CAP_MIN, HORIZON_MIN,
                                              LOAD_POINTS, N_UAVS, distributed_layout,
                                              layout_seed_pairs)
from sim.mission_sim import run_mission_sim

POLICIES = [
    ("baseline", dict(policy="baseline")),
    ("B3", dict(policy="ours", use_queue_term=False)),
]
TOTAL_PADS_DISTRIBUTED = 10  # 10 stations x 1 pad each


def main():
    pairs = layout_seed_pairs()
    t0 = time.time()
    print(f"{'policy':10s} {'rate':>5s} {'completed':>10s} {'total':>7s} {'unfinished':>10s} "
          f"{'station_util':>12s} {'sessions/drone':>14s} {'mean_delay':>10s}")
    for policy_name, kwargs in POLICIES:
        for rate in LOAD_POINTS:
            completed_list, total_list, unfin_list, util_list, sess_per_drone_list, delay_list = \
                [], [], [], [], [], []
            for layout_id, seed in pairs:
                stations = distributed_layout(layout_id)
                r = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=1,
                                     horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=rate,
                                     deadline_window_min=DEADLINE_WINDOW_MIN, drain_cap_min=DRAIN_CAP_MIN,
                                     **kwargs)
                total_charging_time = sum(cs["duration_min"] for cs in r["session_log"])
                utilisation = total_charging_time / (HORIZON_MIN * TOTAL_PADS_DISTRIBUTED)
                delays = [cs["total_delay_min"] for cs in r["session_log"]
                          if cs.get("total_delay_min") is not None]
                completed_list.append(r["missions_completed"])
                total_list.append(r["missions_total"])
                unfin_list.append(r["unfinished_at_cap"])
                util_list.append(utilisation)
                sess_per_drone_list.append(r["charge_sessions"] / N_UAVS)
                delay_list.append(np.mean(delays) if delays else 0.0)
            print(f"{policy_name:10s} {rate:5.1f} {np.mean(completed_list):10.1f} "
                  f"{np.mean(total_list):7.1f} {np.mean(unfin_list):10.1f} "
                  f"{np.mean(util_list):12.4f} {np.mean(sess_per_drone_list):14.2f} "
                  f"{np.mean(delay_list):10.3f}", flush=True)
        print(f"  ({policy_name} done, elapsed={time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
