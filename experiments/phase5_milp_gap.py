"""Phase 5: optimality gap of the greedy least-slack-first heuristic against
the exact MILP, across several random small instances of varying
contention. Reports real numbers -- gap is NOT assumed to be zero."""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.milp import solve_charge_schedule_heuristic, solve_charge_schedule_milp

INSTANCES = [
    dict(n_drones=4, pads=[1, 1], horizon_min=60, dt_min=10, seed=1),
    dict(n_drones=6, pads=[1, 1], horizon_min=90, dt_min=10, seed=2),
    dict(n_drones=8, pads=[1, 1], horizon_min=120, dt_min=10, seed=1),
    dict(n_drones=8, pads=[2, 1], horizon_min=120, dt_min=10, seed=3),
    dict(n_drones=10, pads=[1, 1, 1], horizon_min=120, dt_min=10, seed=4),
    dict(n_drones=10, pads=[1, 1], horizon_min=100, dt_min=10, seed=5),
    dict(n_drones=12, pads=[2, 1], horizon_min=150, dt_min=10, seed=6),
    dict(n_drones=6, pads=[1], horizon_min=90, dt_min=10, seed=7),  # tight: 1 pad only
]


def make_instance(n_drones, seed):
    rng = np.random.default_rng(seed)
    S0 = list(rng.uniform(0.20, 0.35, n_drones))
    required_soc = list(rng.uniform(0.55, 0.85, n_drones))
    return S0, required_soc


def main():
    rows = []
    t0 = time.time()
    for spec in INSTANCES:
        n_drones = spec["n_drones"]
        pads = spec["pads"]
        horizon_min = spec["horizon_min"]
        dt_min = spec["dt_min"]
        T = int(round(horizon_min / dt_min))
        rng = np.random.default_rng(spec["seed"])
        S0, required_soc = make_instance(n_drones, spec["seed"])
        deadline_slot = list(rng.integers(max(2, T // 3), T + 1, n_drones))

        r_milp = solve_charge_schedule_milp(
            n_drones=n_drones, pads=pads, S0=S0, required_soc=required_soc,
            deadline_slot=deadline_slot, horizon_min=horizon_min, dt_min=dt_min,
            battery_wh=90.0, station_rate_w=200.0, sigma=0.20, time_limit_sec=120)
        r_heur = solve_charge_schedule_heuristic(
            n_drones=n_drones, pads=pads, S0=S0, required_soc=required_soc,
            deadline_slot=deadline_slot, horizon_min=horizon_min, dt_min=dt_min,
            battery_wh=90.0, station_rate_w=200.0, sigma=0.20)

        gap = None
        if r_milp["status"] == "Optimal" and r_heur["objective"] is not None:
            gap = (r_heur["objective"] - r_milp["objective"]) / r_milp["objective"]

        row = {
            "n_drones": n_drones, "pads": pads, "horizon_min": horizon_min,
            "milp_status": r_milp["status"], "milp_obj": r_milp["objective"],
            "heur_status": r_heur["status"], "heur_obj": r_heur["objective"],
            "gap": gap,
        }
        rows.append(row)
        print(f"n={n_drones} pads={pads} horizon={horizon_min}  "
              f"MILP={r_milp['status']}/{r_milp['objective']}  "
              f"Heuristic={r_heur['status']}/{r_heur['objective']}  "
              f"gap={f'{gap:.1%}' if gap is not None else 'n/a'}", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase5_milp_gap_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
