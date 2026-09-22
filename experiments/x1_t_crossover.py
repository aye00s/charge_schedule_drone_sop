"""X1 fix: the R1/R3a crossover run used a rho grid designed to bracket
the QUEUE-LENGTH crossover (~0.70-0.83, Table 2), reused for the PRIMARY
wait-time metric too -- but Table 3 shows the wait-time crossover sits
much closer to rho=1 (~1.00-1.02), a completely different location the
old grid never reached, so estimate_crossover_ci correctly reported "no
sign change found" (None). This script uses grids tailored to each
config's actual Table 3 crossover location instead.

Scope note: 15 seeds (not 30) and horizon=30,000 (not 50,000) -- rho near
1.0 is the most expensive region to simulate (highest event rate) and
n=10 configs are already the costliest; full 30-seed/50,000-horizon rigor
here would take multiple hours. This is a first real pass at the
primary metric, not final-rigor numbers.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase1_baseline import t_concentrated
from sim.scheduler import simulate_regime
from sim.stats import estimate_crossover_ci

MU = 1.0
HORIZON = 30_000
SEEDS = list(range(1, 16))
SLACK_MEAN = 1.0 / MU

# Grids tailored to each config's actual Table 3 waiting-time crossover
# (n=4,m=6 ~1.0192; n=5,m=7 ~1.0104; n=10,m=9 ~1.0033 -- very close to 1)
CONFIGS = [
    (4, 6, [1.0001, 1.005, 1.01, 1.015, 1.02, 1.03, 1.05]),
    (5, 7, [1.0001, 1.003, 1.006, 1.009, 1.012, 1.02, 1.03]),
    (10, 9, [1.0001, 1.001, 1.002, 1.003, 1.004, 1.006, 1.01]),
]


def main():
    t0 = time.time()
    all_rows = []
    summary = []

    for n, m, rho_grid in CONFIGS:
        t_r1_by_rho, t_r3a_by_rho = {}, {}
        for rho in rho_grid:
            lam_total = rho * n * MU
            tc_a = t_concentrated(rho, n, m)
            r1_t, r3a_t = [], []
            for seed in SEEDS:
                r1 = simulate_regime(routing="fixed_split", order="fcfs", n_stations=n, capacity=m,
                                      lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                      slack_mean=SLACK_MEAN)
                r3a = simulate_regime(routing="jsq", order="priority", n_stations=n, capacity=m,
                                       lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                       slack_mean=SLACK_MEAN)
                r1_t.append(r1["wait"] * lam_total)
                r3a_t.append(r3a["wait"] * lam_total)
                all_rows.append({"n": n, "m": m, "rho": rho, "seed": seed,
                                  "t_r1": r1["wait"] * lam_total, "t_r3a": r3a["wait"] * lam_total,
                                  "t_c_analytic": tc_a})
            t_r1_by_rho[rho] = r1_t
            t_r3a_by_rho[rho] = r3a_t
            print(f"n={n} m={m} rho={rho:.4f}  R1 t={np.mean(r1_t):.3f}  R3a t={np.mean(r3a_t):.3f}  "
                  f"t_c_analytic={tc_a:.3f}", flush=True)

        tc_by_rho = {r: [t_concentrated(r, n, m)] * len(SEEDS) for r in rho_grid}
        r1_cross = estimate_crossover_ci(rho_grid, tc_by_rho, t_r1_by_rho, seed=2, method="spline")
        r3a_cross = estimate_crossover_ci(rho_grid, tc_by_rho, t_r3a_by_rho, seed=2, method="spline")
        print(f"\n--- n={n} m={m} PRIMARY (per-drone wait t) crossover ---")
        print(f"R1  rho*={r1_cross[0]}, 95% CI=[{r1_cross[1]},{r1_cross[2]}]")
        print(f"R3a rho*={r3a_cross[0]}, 95% CI=[{r3a_cross[1]},{r3a_cross[2]}]\n", flush=True)

        summary.append({"n": n, "m": m,
                         "t_crossover_R1": r1_cross[0], "t_crossover_R1_lo": r1_cross[1], "t_crossover_R1_hi": r1_cross[2],
                         "t_crossover_R3a": r3a_cross[0], "t_crossover_R3a_lo": r3a_cross[1], "t_crossover_R3a_hi": r3a_cross[2]})

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x1_t_crossover_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    summary_path = ROOT / "results" / f"x1_t_crossover_summary_{timestamp}.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)
    print(f"\nWrote {len(all_rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
