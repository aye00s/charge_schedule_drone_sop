"""X1: R3b (jsq_travel) vs the fair concentrated-with-travel baseline,
across >=5 random station layouts (REMEDIATION.md E4(d)'s requirement).

Scope note: horizon=20,000 and 10 seeds/point here, not the full 30-seed/
horizon=50,000 rigor used for R1/R3a's crossover estimate -- 5 layouts x 4
rho x 30 seeds x 2 regimes at horizon=50,000 was estimated at ~3+ hours.
This scope (still real event-driven simulation, not a shortcut) is enough
to see whether the R3b-vs-concentrated crossover is consistent across
layouts or layout-dependent; full rigor on whichever layouts matter can
follow.
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
            r3b_L, conc_L = [], []
            for seed in SEEDS:
                r3b = simulate_regime(routing="jsq_travel", order="priority", n_stations=N, capacity=M,
                                       lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                       slack_mean=SLACK_MEAN, layout_seed=layout_seed)
                rc = simulate_concentrated_with_travel(n_servers=N, capacity=N * M, lam_total=lam_total,
                                                        mu=MU, horizon=HORIZON, seed=seed, hub_position=hub,
                                                        order="priority", slack_mean=SLACK_MEAN)
                r3b_L.append(r3b["L"]); conc_L.append(rc["L"])
                rows.append({"layout_seed": layout_seed, "rho": rho, "seed": seed,
                             "R3b_L": r3b["L"], "Concentrated_travel_L": rc["L"],
                             "R3b_block": r3b["block_frac"], "Concentrated_block": rc["block_frac"]})
            print(f"layout={layout_seed} rho={rho:.1f}  R3b L={np.mean(r3b_L):.3f}  "
                  f"Concentrated+travel L={np.mean(conc_L):.3f}  "
                  f"winner={'R3b' if np.mean(r3b_L) < np.mean(conc_L) else 'Concentrated'}", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x1_r3b_layouts_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
