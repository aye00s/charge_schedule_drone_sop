"""Phase 3, statistical rigor: 30-seed CRN comparison of R1 (plain
distributed) vs R3a (JSQ routing) against the concentrated analytic
baseline, with a bootstrap CI on the crossover shift (Section 7: >=30
seeds, bootstrap rather than plain bisection on noisy output) plus a
paired Wilcoxon test on L at each rho.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase1_baseline import L_concentrated
from sim.scheduler import simulate_regime
from sim.stats import bootstrap_ci, estimate_crossover_ci, paired_test

MU = 1.0
HORIZON = 50_000
SEEDS = list(range(1, 31))
SLACK_MEAN = 1.0 / MU
N, M = 5, 7
RHO_VALUES = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]


def main():
    t0 = time.time()
    L_r1_by_rho = {}
    L_r3a_by_rho = {}
    rows = []

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
            rows.append({"rho": rho, "seed": seed, "L_r1": r1["L"], "L_r3a": r3a["L"], "L_c_analytic": Lc_a})
        L_r1_by_rho[rho] = r1_vals
        L_r3a_by_rho[rho] = r3a_vals
        m1, lo1, hi1 = bootstrap_ci(r1_vals, seed=1)
        m3a, lo3a, hi3a = bootstrap_ci(r3a_vals, seed=1)
        print(f"rho={rho:.2f}  R1 L={m1:.3f} [{lo1:.3f},{hi1:.3f}]  "
              f"R3a L={m3a:.3f} [{lo3a:.3f},{hi3a:.3f}]  L_c_analytic={Lc_a:.3f}", flush=True)

    # crossover of R1 vs L_c_analytic (constant per rho, so "seeds" for L_c_analytic are all equal)
    Lc_by_rho = {rho: [L_concentrated(rho, N, M)] * len(SEEDS) for rho in RHO_VALUES}
    r1_cross = estimate_crossover_ci(RHO_VALUES, Lc_by_rho, L_r1_by_rho, seed=2)
    r3a_cross = estimate_crossover_ci(RHO_VALUES, Lc_by_rho, L_r3a_by_rho, seed=2)
    print(f"\nR1 vs L_c crossover (rho*): point={r1_cross[0]}, 95% CI=[{r1_cross[1]}, {r1_cross[2]}]")
    print(f"R3a vs L_c crossover (rho*): point={r3a_cross[0]}, 95% CI=[{r3a_cross[1]}, {r3a_cross[2]}]")

    print("\nPaired Wilcoxon test, R1 vs R3a on L, at each rho:")
    for rho in RHO_VALUES:
        stat, p = paired_test(L_r1_by_rho[rho], L_r3a_by_rho[rho])
        print(f"  rho={rho:.2f}  p={p:.2e}  {'significant' if p < 0.05 else 'not significant'} (alpha=0.05)")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase3_crossover_ci_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
