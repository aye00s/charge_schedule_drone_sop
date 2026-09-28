"""Follow-up to X7, per user instruction (2026-09-24): report scheduler
runtime per decision for `ours` alongside MILP v2 solve times, so H6's
refutation (X7: 71.4%-109.2% mean gap) is shown next to the cost of
optimality it buys -- and to make concrete the claim (Section 4.6) that
the MILP is impractical past roughly N=15 drones, which `ours` is not.

Part A: `ours`'s runtime_per_decision_us (already computed by
sim/mission_sim.py, wall-clock around the dispatch-decision block only,
divided by drones actually dispatched) at fleet sizes 5/10/20/40/60,
mirroring HISTORY.md's original Phase 6 fleet-size axis.

Part B: MILP v2 solve wall-clock time vs n_drones, using X7's own
instance generator, extended past X7's own n<=8 grid to find where it
stops finishing inside a fixed time budget.

Usage: `python experiments/x7_runtime_comparison.py`
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from experiments.x7_milp_v2_gap import BATTERY_WH, DT_MIN, SIGMA, generate_instance
from sim.milp import solve_charge_schedule_milp_v2
from sim.mission_sim import run_mission_sim

TIME_LIMIT_SEC = 120


def part_a():
    print("=== Part A: ours's runtime_per_decision_us vs fleet size ===\n")
    configs = [
        (5, 2, 0.4), (10, 3, 0.4), (20, 5, 0.8), (40, 10, 0.8), (60, 15, 0.8),
    ]
    for n_uavs, n_stations, rate in configs:
        rng = np.random.default_rng(2000 + n_stations)
        stations = [tuple(rng.uniform(0, 2000.0, size=2)) for _ in range(n_stations)]
        rt_us = []
        for seed in (1, 2, 3):
            r = run_mission_sim(n_uavs=n_uavs, station_positions=stations, pads_per_station=2,
                                 horizon_min=1000.0, seed=seed, mission_rate_per_min=rate,
                                 deadline_window_min=45.0, drain_cap_min=135.0, policy="ours")
            rt_us.append(r["runtime_per_decision_us"])
        print(f"  n_uavs={n_uavs:3d} n_stations={n_stations:2d}  "
              f"runtime_per_decision = {np.mean(rt_us):8.2f} us (mean of 3 seeds)")


def part_b():
    print("\n=== Part B: MILP v2 solve wall-clock time vs n_drones ===\n")
    for n_drones, n_stations in [(2, 1), (4, 1), (6, 2), (8, 3), (10, 3), (12, 4), (15, 4)]:
        times = []
        statuses = []
        for seed in (1, 2, 3):
            inst = generate_instance(n_drones, n_stations, seed)
            t0 = time.time()
            try:
                r = solve_charge_schedule_milp_v2(
                    n_drones=inst["n_drones"], pads=inst["pads"], S0=inst["S0"], missions=inst["missions"],
                    battery_wh=BATTERY_WH, sigma=SIGMA, horizon_min=inst["horizon_min"], dt_min=DT_MIN,
                    time_limit_sec=TIME_LIMIT_SEC)
                dt = time.time() - t0
                times.append(dt)
                statuses.append(r["status"])
                print(f"    n_drones={n_drones} seed={seed}: {dt:.2f}s status={r['status']}", flush=True)
            except Exception as e:
                dt = time.time() - t0
                print(f"    n_drones={n_drones} seed={seed}: FAILED after {dt:.2f}s ({type(e).__name__}: "
                      f"{str(e)[:150]})", flush=True)
                statuses.append("ERROR")
        if times:
            print(f"  n_drones={n_drones:2d} n_stations={n_stations}  "
                  f"solve_time = {np.mean(times):7.2f}s (mean of {len(times)} successful seeds, range "
                  f"[{min(times):.2f},{max(times):.2f}])  statuses={statuses}")
        if any(s != "Optimal" for s in statuses):
            print(f"    -> NOT solved to proven optimality within {TIME_LIMIT_SEC}s at n_drones={n_drones} "
                  f"for at least one seed; stopping the sweep here.")
            break


if __name__ == "__main__":
    part_a()
    part_b()
