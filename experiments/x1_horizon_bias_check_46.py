"""Follow-up to x1_horizon_bias_check.py, re-targeted after a transcription
bug was found in CLAUDE.md: the (10,9) row of Table 3 was misquoted as
1.00321 (that is actually the m=8 value); the real Table 3 value for
(10,9) is 1.002478466796875, which the ORIGINAL horizon=30,000 CI
[1.00236, 1.00275] already contained. So (10,9) was never actually a
miss, and the horizon=200,000 re-run of it (x1_horizon_bias_check.py)
was not the config that needed it.

The real miss, once the table is read correctly, is (4,6): CI
[1.01597, 1.01899] vs the correct analytic 1.019188720703125 -- the
analytic value sits just above the CI's upper bound. Re-running (4,6)
at horizon=200,000 (vs the original 30,000) and 15% warm-up (vs 10%),
exactly mirroring the method used for the (10,9) check, to see whether
this is the same finite-horizon bias signature.
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
N, M = 4, 6
RHO_GRID = [1.0001, 1.005, 1.01, 1.015, 1.02, 1.03, 1.05]


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
    print(f"Table 3 (n=4,m=6): 1.019188720703125")
    print(f"Gap: {r1_cross[0] - true_val:+.6f}  (original horizon=30,000 run had gap "
          f"{1.017596 - true_val:+.6f}, CI [1.01597,1.01899] which did NOT contain the true value)")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x1_horizon_bias_check_46_{timestamp}.csv"
    with open(out_path, "w", newline="") as f2:
        writer = csv.DictWriter(f2, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
