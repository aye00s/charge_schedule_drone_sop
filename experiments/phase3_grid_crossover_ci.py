"""Phase 3: extend the 30-seed crossover-CI rigor to 2 more (n,m) points
spanning the grid extremes (n=4,m=6 and n=10,m=9), alongside the existing
n=5,m=7 result, to check the crossover-shift finding generalizes. The full
28-point grid at this rigor is computationally infeasible in one sitting
(~27 hours extrapolated from this run's cost) -- this is a representative
subset, not the full deliverable, and that's stated plainly rather than
silently substituted.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase1_baseline import L_concentrated
from sim.scheduler import simulate_regime
from sim.stats import bootstrap_ci, estimate_crossover_ci, paired_test

MU = 1.0
HORIZON = 50_000
SEEDS = list(range(1, 31))
SLACK_MEAN = 1.0 / MU

# (n, m, rho_grid) -- rho grid bracketing each pair's own analytical
# crossover from Table 2 (n=4,m=6: rho*=0.7075; n=10,m=9: rho*=0.8253)
CONFIGS = [
    (4, 6, [0.55, 0.60, 0.65, 0.70, 0.75]),
    (10, 9, [0.70, 0.75, 0.80, 0.85, 0.90]),
]


def main():
    t0 = time.time()
    all_rows = []
    for N, M, RHO_VALUES in CONFIGS:
        L_r1_by_rho = {}
        L_r3a_by_rho = {}
        for rho in RHO_VALUES:
            lam_total = rho * N * MU
            Lc_a = L_concentrated(rho, N, M)
            r1_vals, r3a_vals = [], []
            for seed in SEEDS:
                r1 = simulate_regime(routing="fixed_split", order="fcfs", n_stations=N, capacity=M,
                                      lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                      slack_mean=SLACK_MEAN)
                r3a = simulate_regime(routing="jsq", order="priority", n_stations=N, capacity=M,
                                       lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                       slack_mean=SLACK_MEAN)
                r1_vals.append(r1["L"])
                r3a_vals.append(r3a["L"])
                all_rows.append({"n": N, "m": M, "rho": rho, "seed": seed,
                                  "L_r1": r1["L"], "L_r3a": r3a["L"], "L_c_analytic": Lc_a})
            L_r1_by_rho[rho] = r1_vals
            L_r3a_by_rho[rho] = r3a_vals
            m1, lo1, hi1 = bootstrap_ci(r1_vals, seed=1)
            m3a, lo3a, hi3a = bootstrap_ci(r3a_vals, seed=1)
            print(f"n={N} m={M} rho={rho:.2f}  R1 L={m1:.3f} [{lo1:.3f},{hi1:.3f}]  "
                  f"R3a L={m3a:.3f} [{lo3a:.3f},{hi3a:.3f}]  L_c_analytic={Lc_a:.3f}", flush=True)

        Lc_by_rho = {rho: [L_concentrated(rho, N, M)] * len(SEEDS) for rho in RHO_VALUES}
        r1_cross = estimate_crossover_ci(RHO_VALUES, Lc_by_rho, L_r1_by_rho, seed=2)
        r3a_cross = estimate_crossover_ci(RHO_VALUES, Lc_by_rho, L_r3a_by_rho, seed=2)
        print(f"n={N} m={M}: R1 vs L_c crossover rho*={r1_cross[0]}, CI=[{r1_cross[1]},{r1_cross[2]}]")
        print(f"n={N} m={M}: R3a vs L_c crossover rho*={r3a_cross[0]}, CI=[{r3a_cross[1]},{r3a_cross[2]}]")
        print(flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase3_grid_crossover_ci_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
