"""Phase 5, robustness check: does the 0% optimality gap hold across many
random instances per configuration, or was the earlier 8-instance sweep
(1 random draw each) just lucky? Runs 5 random seeds per configuration."""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.milp import solve_charge_schedule_heuristic, solve_charge_schedule_milp

CONFIGS = [
    dict(n_drones=6, pads=[1, 1], horizon_min=90, dt_min=10),
    dict(n_drones=8, pads=[2, 1], horizon_min=120, dt_min=10),
    dict(n_drones=10, pads=[1, 1, 1], horizon_min=120, dt_min=10),
]
SEEDS = [101, 102, 103, 104, 105]


def main():
    t0 = time.time()
    rows = []
    gaps = []
    for cfg in CONFIGS:
        n_drones = cfg["n_drones"]
        pads = cfg["pads"]
        horizon_min = cfg["horizon_min"]
        dt_min = cfg["dt_min"]
        T = int(round(horizon_min / dt_min))
        for seed in SEEDS:
            rng = np.random.default_rng(seed)
            S0 = list(rng.uniform(0.20, 0.35, n_drones))
            required_soc = list(rng.uniform(0.55, 0.85, n_drones))
            deadline_slot = list(rng.integers(max(2, T // 3), T + 1, n_drones))

            r_milp = solve_charge_schedule_milp(
                n_drones=n_drones, pads=pads, S0=S0, required_soc=required_soc,
                deadline_slot=deadline_slot, horizon_min=horizon_min, dt_min=dt_min,
                battery_wh=90.0, station_rate_w=200.0, sigma=0.20, time_limit_sec=90)
            r_heur = solve_charge_schedule_heuristic(
                n_drones=n_drones, pads=pads, S0=S0, required_soc=required_soc,
                deadline_slot=deadline_slot, horizon_min=horizon_min, dt_min=dt_min,
                battery_wh=90.0, station_rate_w=200.0, sigma=0.20)

            gap = None
            if r_milp["status"] == "Optimal" and r_heur["objective"] is not None:
                gap = (r_heur["objective"] - r_milp["objective"]) / r_milp["objective"]
                gaps.append(gap)
            rows.append({"n_drones": n_drones, "pads": str(pads), "seed": seed,
                        "milp_status": r_milp["status"], "milp_obj": r_milp["objective"],
                        "heur_obj": r_heur["objective"], "gap": gap})
            print(f"n={n_drones} pads={pads} seed={seed}  MILP={r_milp['status']}/{r_milp['objective']}  "
                  f"Heuristic={r_heur['objective']}  gap={f'{gap:.1%}' if gap is not None else 'n/a'}",
                  flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase5_gap_robustness_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(gaps)} feasible instances; gaps: {gaps}")
    print(f"nonzero gaps found: {sum(1 for g in gaps if abs(g) > 1e-9)}")
    print(f"Wrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
