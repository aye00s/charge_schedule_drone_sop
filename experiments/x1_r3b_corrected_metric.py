"""Fix for TWO real bugs caught in sequence:
1. (caught by the user) the earlier R3b vs concentrated-with-travel
   comparison used simulate_regime's L (per-STATION average, i.e.
   per-pad -- divided by n_stations) against
   simulate_concentrated_with_travel's L (the WHOLE HUB's total, not
   divided) -- the exact per-pad-vs-whole-hub category error E1 was
   supposed to have fixed, just recommitted in a new place.
2. (caught while fixing #1) the first "fix" then used `wait` (on-pad
   delay ONLY, explicitly excludes travel per this module's own
   docstring) as the "primary metric", not `total_delay` (which DOES
   include travel, matching E4(c)'s own accounting rule: "a drone's
   charging delay is always measured as charge_start - charge_request_
   time, regardless of where it waited"). `total_delay` is also NOT
   rescaled by lam_total in simulate_regime's return value (only `wait`
   is) -- multiplying `wait` by lam_total and comparing it directly
   against unrescaled `total_delay` mixed two different scalings.
Redone here with:
  - PRIMARY: total_delay * lam_total (request-to-service-start,
    including travel, properly rescaled to match the paper convention
    used everywhere else).
  - SECONDARY: total queue length (n * R3b's per-station L, vs
    Concentrated's L which is already the system total).
  - blocking probability, both sides.
Across the same 5 station layouts as before.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.scheduler import centroid, simulate_concentrated_with_travel, simulate_regime, _station_positions

MU = 1.0
HORIZON = 20_000
SEEDS = list(range(1, 11))
SLACK_MEAN = 1.0 / MU
N, M = 5, 7
RHO_VALUES = [0.6, 0.8, 1.0, 1.2]
LAYOUT_SEEDS = [0, 1, 2, 3, 4]


def main():
    t0 = time.time()
    rows = []
    for layout_seed in LAYOUT_SEEDS:
        stations = _station_positions(N, layout_seed)
        hub = centroid(stations)
        for rho in RHO_VALUES:
            lam_total = rho * N * MU
            r3b_t, r3b_totalL, r3b_block = [], [], []
            conc_t, conc_L, conc_block = [], [], []
            for seed in SEEDS:
                r3b = simulate_regime(routing="jsq_travel", order="priority", n_stations=N, capacity=M,
                                       lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                       slack_mean=SLACK_MEAN, layout_seed=layout_seed)
                rc = simulate_concentrated_with_travel(n_servers=N, capacity=N * M, lam_total=lam_total,
                                                        mu=MU, horizon=HORIZON, seed=seed, hub_position=hub,
                                                        order="priority", slack_mean=SLACK_MEAN)
                r3b_t.append(r3b["total_delay"] * lam_total)
                r3b_totalL.append(r3b["L"] * N)  # per-station avg * n_stations = system total
                r3b_block.append(r3b["block_frac"])
                conc_t.append(rc["total_delay"] * lam_total)
                conc_L.append(rc["L"])  # already system total
                conc_block.append(rc["block_frac"])
                rows.append({"layout_seed": layout_seed, "rho": rho, "seed": seed,
                            "t_r3b": r3b["total_delay"] * lam_total, "t_conc": rc["total_delay"] * lam_total,
                            "totalL_r3b": r3b["L"] * N, "totalL_conc": rc["L"],
                            "block_r3b": r3b["block_frac"], "block_conc": rc["block_frac"]})
            t_winner = "R3b" if np.mean(r3b_t) < np.mean(conc_t) else "Concentrated"
            L_winner = "R3b" if np.mean(r3b_totalL) < np.mean(conc_L) else "Concentrated"
            print(f"layout={layout_seed} rho={rho:.1f}  "
                  f"t: R3b={np.mean(r3b_t):7.3f} Conc={np.mean(conc_t):7.3f} (winner={t_winner})  "
                  f"totalL: R3b={np.mean(r3b_totalL):7.3f} Conc={np.mean(conc_L):7.3f} (winner={L_winner})  "
                  f"block: R3b={np.mean(r3b_block):.4f} Conc={np.mean(conc_block):.4f}", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x1_r3b_corrected_metric_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
