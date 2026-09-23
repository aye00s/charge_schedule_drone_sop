"""Follow-up to X7 (2026-09-23, per user instruction): the original X7
sweep's deadline_min=100 (10 slots) was generous enough that BOTH v1 and
v2 always meet every deadline -- tardiness contributes exactly 0 to the
gap in all 24 instances, so the headline 71.4% mean gap is entirely
makespan+energy, measured in a regime where the deadline constraint never
binds. That is not the regime `ours` (a deadline-aware scheduler) is
designed for. This script re-runs the SAME 24 instances (same configs,
same seeds, same station/S0/mission draws) with deadline_min=25 and
horizon_min=50 (vs 100/120) -- tight enough that tardiness is nonzero for
at least one solver (probed directly: at n=6, MILP tardy=5.0, heuristic
tardy=35.0, both nonzero) while every instance still generates without a
ValueError (no mission has zero feasible start slots).

Usage: `python experiments/x7_tight_deadline_gap.py`
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.x7_milp_v2_gap import (BATTERY_WH, DT_MIN, SIGMA, V1_TIME_LIMIT_SEC, V2_TIME_LIMIT_SEC,
                                          generate_instance)
from sim.milp import (solve_charge_schedule_heuristic, solve_charge_schedule_milp,
                       solve_charge_schedule_milp_v2, solve_charge_schedule_ours_v2)

DEADLINE_MIN = 25.0
HORIZON_MIN = 50.0


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
    v1_gap = None
    if T_v1["status"] == "Optimal" and H_v1["status"] != "Infeasible" and T_v1["objective"]:
        v1_gap = (H_v1["objective"] - T_v1["objective"]) / T_v1["objective"]

    T_v2 = solve_charge_schedule_milp_v2(
        n_drones=inst["n_drones"], pads=inst["pads"], S0=inst["S0"], missions=inst["missions"],
        battery_wh=BATTERY_WH, sigma=SIGMA, horizon_min=inst["horizon_min"], dt_min=DT_MIN,
        time_limit_sec=V2_TIME_LIMIT_SEC)
    H_v2 = solve_charge_schedule_ours_v2(
        n_drones=inst["n_drones"], pads=inst["pads"], S0=inst["S0"], missions=inst["missions"],
        battery_wh=BATTERY_WH, sigma=SIGMA, horizon_min=inst["horizon_min"], dt_min=DT_MIN)

    v2_gap = None
    if T_v2["is_optimal"] and H_v2["status"] == "Heuristic" and T_v2["objective"]:
        v2_gap = (H_v2["objective"] - T_v2["objective"]) / T_v2["objective"]

    return dict(
        v1_status=T_v1["status"], v1_gap=v1_gap,
        v2_status=T_v2["status"], v2_optimal=T_v2["is_optimal"], v2_gap=v2_gap,
        milp_cmax=T_v2["alpha_cmax_term"], heur_cmax=H_v2.get("alpha_cmax_term"),
        milp_energy=T_v2["beta_energy_term"], heur_energy=H_v2.get("beta_energy_term"),
        milp_tardy=T_v2["gamma_tardy_term"], heur_tardy=H_v2.get("total_tardiness"),
        heur_status=H_v2["status"],
    )


def main():
    configs = [(2, 1), (3, 1), (4, 2), (4, 1), (5, 2), (6, 2), (6, 3), (8, 3)]
    seeds = [1, 2, 3]
    total = len(configs) * len(seeds)
    print(f"X7 tight-deadline variant: {total} instances, deadline_min={DEADLINE_MIN}, horizon_min={HORIZON_MIN}")
    t0 = time.time()
    rows = []
    for n_drones, n_stations in configs:
        for seed in seeds:
            inst = generate_instance(n_drones, n_stations, seed, horizon_min=HORIZON_MIN, deadline_min=DEADLINE_MIN)
            r = run_one(inst)
            r.update(n_drones=n_drones, n_stations=n_stations, seed=seed)
            rows.append(r)
            print(f"  n={n_drones} st={n_stations} seed={seed}: v1_gap={r['v1_gap']} v2_gap={r['v2_gap']} "
                  f"milp_tardy={r['milp_tardy']} heur_tardy={r['heur_tardy']} elapsed={time.time()-t0:.1f}s",
                  flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x7_tight_deadline_gap_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    v1_gaps = [r["v1_gap"] for r in rows if r["v1_gap"] is not None]
    v2_gaps = [r["v2_gap"] for r in rows if r["v2_gap"] is not None]
    n_binding = sum(1 for r in rows if (r["milp_tardy"] or 0) > 0 or (r["heur_tardy"] or 0) > 0)
    print(f"\nInstances where the deadline constraint binds for at least one solver: {n_binding}/{len(rows)}")
    print(f"v1: mean gap = {np.mean(v1_gaps) if v1_gaps else 'n/a'} (n={len(v1_gaps)})")
    print(f"v2: mean gap = {np.mean(v2_gaps) if v2_gaps else 'n/a'} (n={len(v2_gaps)})")
    if v2_gaps:
        print(f"v2 gap distribution: {sorted(round(g, 4) for g in v2_gaps)}")


if __name__ == "__main__":
    main()
