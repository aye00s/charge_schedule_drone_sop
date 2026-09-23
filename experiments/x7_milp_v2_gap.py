"""REMEDIATION.md checkpoint 7, X7: MILP v2 optimality-gap sweep, with v1
run side by side on the SAME underlying instances (addition 1, per user
instruction 2026-09-23) to show that v1's historical 0% gap is a property
of its constant pad-slot-count objective, not evidence the heuristic is
truly optimal (E10).

"Same instance" (addition 1), operationalised: each generated instance has
one canonical set of {n_drones, station pad counts, initial SoC S0}. A
mission list (duration/energy/release/deadline) is drawn for v2's real
problem; v1 (which has no mission concept at all -- it only ever modelled
"reach a required SoC by a deadline") is given a DERIVED required_soc/
deadline_slot per drone, reflecting the SAME instance's actual charging
demand (required_soc[i] = sigma + mean mission energy / battery_wh,
deadline_slot from the same deadline_min). This is the closest "same
instance" can mean given v1's model literally cannot represent missions --
documented here rather than silently assumed.

Addition 3 (solver time limit / reporting rule): time_limit_sec is set
BEFORE running (120s per v1/ccv-style call, 180s for v2 given its larger
variable count); gap is computed ONLY when is_optimal (v2) / status ==
"Optimal" (v1) -- a timed-out incumbent is reported as such, gap left as
None, never silently treated as optimal.

Addition 4 (capacity invariant): already enforced INSIDE
solve_charge_schedule_milp_v2 and solve_charge_schedule_ours_v2 themselves
(raises AssertionError on any C1 violation in the returned solution) --
this script additionally reports "capacity_checked": True per row so it is
visible in the results CSV, not just implicit.

Usage: `python experiments/x7_milp_v2_gap.py --pilot` for a small
timing/correctness check; no flag for the full run.
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

from sim.milp import (solve_charge_schedule_heuristic, solve_charge_schedule_milp,
                       solve_charge_schedule_milp_v2, solve_charge_schedule_ours_v2)

SIGMA = 0.20
BATTERY_WH = 90.0
DT_MIN = 10.0
V1_TIME_LIMIT_SEC = 60
V2_TIME_LIMIT_SEC = 180


def generate_instance(n_drones, n_stations, seed, horizon_min=120.0, deadline_min=100.0):
    rng = np.random.default_rng(seed)
    pads = [int(rng.integers(1, 3)) for _ in range(n_stations)]  # 1-2 pads/station
    S0 = [float(rng.uniform(0.20, 0.45)) for _ in range(n_drones)]
    k_missions = n_drones  # one mission per drone, keeps K<=8 per REMEDIATION's own bound
    missions = []
    for _ in range(k_missions):
        e = float(rng.uniform(5.0, 15.0))
        d = int(rng.integers(1, 3))
        missions.append(dict(duration_slots=d, energy_wh=e, release_slot=0, deadline_min=deadline_min))

    avg_energy = float(np.mean([m["energy_wh"] for m in missions]))
    required_soc = [min(1.0, SIGMA + avg_energy / BATTERY_WH) for _ in range(n_drones)]
    deadline_slot = [int(round(deadline_min / DT_MIN))] * n_drones

    return dict(n_drones=n_drones, pads=pads, S0=S0, missions=missions, horizon_min=horizon_min,
                required_soc=required_soc, deadline_slot=deadline_slot, deadline_min=deadline_min)


def run_one(inst):
    T_v1 = solve_charge_schedule_milp(
        n_drones=inst["n_drones"], pads=inst["pads"], S0=inst["S0"],
        required_soc=inst["required_soc"], deadline_slot=inst["deadline_slot"],
        horizon_min=inst["horizon_min"], dt_min=DT_MIN, battery_wh=BATTERY_WH,
        sigma=SIGMA, time_limit_sec=V1_TIME_LIMIT_SEC)
    H_v1 = solve_charge_schedule_heuristic(
        n_drones=inst["n_drones"], pads=inst["pads"], S0=inst["S0"],
        required_soc=inst["required_soc"], deadline_slot=inst["deadline_slot"],
        horizon_min=inst["horizon_min"], dt_min=DT_MIN, battery_wh=BATTERY_WH, sigma=SIGMA)

    v1_optimal = (T_v1["status"] == "Optimal")
    v1_feasible = (H_v1["status"] != "Infeasible")
    v1_gap = None
    if v1_optimal and v1_feasible and T_v1["objective"] not in (None, 0):
        v1_gap = (H_v1["objective"] - T_v1["objective"]) / T_v1["objective"]
    elif v1_optimal and v1_feasible and T_v1["objective"] == 0:
        v1_gap = 0.0 if H_v1["objective"] == 0 else float("inf")

    try:
        T_v2 = solve_charge_schedule_milp_v2(
            n_drones=inst["n_drones"], pads=inst["pads"], S0=inst["S0"], missions=inst["missions"],
            battery_wh=BATTERY_WH, sigma=SIGMA, horizon_min=inst["horizon_min"], dt_min=DT_MIN,
            time_limit_sec=V2_TIME_LIMIT_SEC)
        v2_status = T_v2["status"]
        v2_optimal = T_v2["is_optimal"]
        v2_obj = T_v2["objective"]
    except ValueError as e:  # a mission has no feasible start slot in this instance
        return dict(v1_status=T_v1["status"], v1_gap=v1_gap, v2_status=f"SKIPPED: {e}",
                    v2_optimal=False, v2_gap=None, heur_status="SKIPPED")

    try:
        H_v2 = solve_charge_schedule_ours_v2(
            n_drones=inst["n_drones"], pads=inst["pads"], S0=inst["S0"], missions=inst["missions"],
            battery_wh=BATTERY_WH, sigma=SIGMA, horizon_min=inst["horizon_min"], dt_min=DT_MIN)
        heur_status = H_v2["status"]
        heur_obj = H_v2["objective"]
    except AssertionError as e:  # capacity invariant fired -- report, don't crash the sweep
        heur_status = f"CAPACITY_VIOLATION: {e}"
        heur_obj = None

    v2_gap = None
    # Addition 3's rule: only ever compute a gap when v2_optimal is True.
    if v2_optimal and heur_status == "Heuristic" and heur_obj is not None and v2_obj not in (None, 0):
        v2_gap = (heur_obj - v2_obj) / v2_obj

    return dict(
        v1_status=T_v1["status"], v1_objective=T_v1["objective"], v1_heur_objective=H_v1["objective"],
        v1_gap=v1_gap,
        v2_status=v2_status, v2_optimal=v2_optimal, v2_objective=v2_obj,
        heur_status=heur_status, heur_objective=heur_obj, v2_gap=v2_gap,
        capacity_checked=True,
    )


def run_pilot():
    print("PILOT: 3 small instances\n")
    t0 = time.time()
    for n_drones, n_stations, seed in [(2, 1, 1), (4, 2, 2), (6, 2, 3)]:
        inst = generate_instance(n_drones, n_stations, seed)
        rt0 = time.time()
        r = run_one(inst)
        rt = time.time() - rt0
        print(f"n={n_drones} stations={n_stations} seed={seed} runtime={rt:.1f}s -> {r}")
    total_s = time.time() - t0
    print(f"\nPilot: 3 instances in {total_s:.1f}s ({total_s/3:.1f}s/instance average)")
    est_s = total_s / 3 * 20
    print(f"Estimated for >=20 instances: {est_s/60:.1f} min ({est_s:.0f}s)")


def run_full():
    configs = [(2, 1), (3, 1), (4, 2), (4, 1), (5, 2), (6, 2), (6, 3), (8, 3)]
    seeds = [1, 2, 3]
    total = len(configs) * len(seeds)
    print(f"Full X7: {len(configs)} configs x {len(seeds)} seeds = {total} instances")
    t0 = time.time()
    rows = []
    for n_drones, n_stations in configs:
        for seed in seeds:
            inst = generate_instance(n_drones, n_stations, seed)
            r = run_one(inst)
            r.update(n_drones=n_drones, n_stations=n_stations, seed=seed)
            rows.append(r)
            print(f"  n={n_drones} stations={n_stations} seed={seed}: v1_gap={r.get('v1_gap')} "
                  f"v2_status={r.get('v2_status')} v2_gap={r.get('v2_gap')} "
                  f"elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x7_milp_v2_gap_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    print("\n=== v1 vs v2 gap, side by side ===")
    v1_gaps = [r["v1_gap"] for r in rows if r.get("v1_gap") is not None]
    v2_gaps = [r["v2_gap"] for r in rows if r.get("v2_gap") is not None]
    n_v1_optimal = sum(1 for r in rows if r["v1_status"] == "Optimal")
    n_v2_optimal = sum(1 for r in rows if r.get("v2_optimal"))
    print(f"v1: {n_v1_optimal}/{len(rows)} instances solved Optimal, "
          f"mean gap = {np.mean(v1_gaps) if v1_gaps else 'n/a'} (n={len(v1_gaps)})")
    print(f"v2: {n_v2_optimal}/{len(rows)} instances solved Optimal, "
          f"mean gap = {np.mean(v2_gaps) if v2_gaps else 'n/a'} (n={len(v2_gaps)})")
    if v1_gaps:
        print(f"v1 gap distribution: {sorted(round(g, 4) for g in v1_gaps)}")
    if v2_gaps:
        print(f"v2 gap distribution: {sorted(round(g, 4) for g in v2_gaps)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.pilot:
        run_pilot()
    else:
        run_full()
