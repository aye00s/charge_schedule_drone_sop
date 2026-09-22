"""User-requested check: are the R1 t-crossover CI misses at (4,6) and
(10,9) genuine bias (finite-horizon, since rho~1 is a slow-mixing
heavy-traffic regime) rather than just estimator variance? Fewer seeds
widen a CI but don't shift its center -- a shift implicates the horizon,
not the seed count. Re-running n=10,m=9 (the worse miss, crossover very
close to rho=1 at ~1.0032, the most heavy-traffic-adjacent case) with
horizon=200,000 (vs the original 30,000) and 15% warm-up (vs 10%).
If the gap to the analytic value closes, that confirms finite-horizon
bias, not an estimator problem -- and CLAUDE.md's explanation gets
corrected either way, per the user's instruction.
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
HORIZON = 200_000
WARMUP_FRAC = 0.15
SEEDS = list(range(1, 11))
SLACK_MEAN = 1.0 / MU
N, M = 10, 9
RHO_GRID = [1.0001, 1.001, 1.002, 1.003, 1.004, 1.006, 1.01]


def main():
    t0 = time.time()
    rows = []
    t_r1_by_rho = {}
    for rho in RHO_GRID:
        lam_total = rho * N * MU
        tc_a = t_concentrated(rho, N, M)
        r1_t = []
        for seed in SEEDS:
            r1 = simulate_regime(routing="fixed_split", order="fcfs", n_stations=N, capacity=M,
                                  lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                  slack_mean=SLACK_MEAN, warmup_frac=WARMUP_FRAC)
            r1_t.append(r1["wait"] * lam_total)
            rows.append({"rho": rho, "seed": seed, "t_r1": r1["wait"] * lam_total, "t_c_analytic": tc_a})
        t_r1_by_rho[rho] = r1_t
        print(f"rho={rho:.4f}  R1 t={np.mean(r1_t):.4f} (std={np.std(r1_t):.4f})  t_c_analytic={tc_a:.4f}",
              flush=True)

    tc_by_rho = {r: [t_concentrated(r, N, M)] * len(SEEDS) for r in RHO_GRID}
    r1_cross = estimate_crossover_ci(RHO_GRID, tc_by_rho, t_r1_by_rho, seed=2, method="spline")
    print(f"\n--- n={N} m={M}, horizon={HORIZON}, warmup={WARMUP_FRAC} ---")
    print(f"R1 t-crossover rho*={r1_cross[0]}, 95% CI=[{r1_cross[1]},{r1_cross[2]}]")

    from phase1_baseline import bisect, t_distributed
    f = lambda rho: t_distributed(rho, M, N) - t_concentrated(rho, N, M)
    true_val = bisect(f, 1.0001, 1.10, tol=1e-9)
    print(f"True analytic crossover (fine bisect): {true_val:.6f}")
    print(f"Gap: {r1_cross[0] - true_val:+.6f}  (previous horizon=30,000 run had gap "
          f"{1.0025813067482956 - true_val:+.6f})")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x1_horizon_bias_check_{timestamp}.csv"
    with open(out_path, "w", newline="") as f2:
        writer = csv.DictWriter(f2, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
