"""Phase 3 regime comparison: R1 (FCFS, fixed-split) vs R2 (priority,
fixed-split) vs R3a (priority, scheduler-chosen pad / JSQ), against the
Phase 1 concentrated analytic L_c as the benchmark distributed charging is
trying to close the gap to. Writes one row per (n, m, rho, seed, regime) to
a timestamped CSV under results/.

This is an exploratory run (5 seeds), not the final Phase 6 statistics
(>=30 seeds, CRN, bootstrap CIs) -- it is meant to show the qualitative
trend and get real numbers before committing to a larger sweep.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase1_baseline import L_concentrated, L_distributed
from sim.scheduler import simulate_regime

MU = 1.0
HORIZON = 50_000
SEEDS = list(range(1, 16))
SLACK_MEAN = 1.0 / MU
N, M = 5, 7
RHO_VALUES = [0.6, 0.65, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]

REGIMES = {
    "R1_fcfs_fixed": dict(routing="fixed_split", order="fcfs"),
    "R2_priority_fixed": dict(routing="fixed_split", order="priority"),
    "R3a_priority_jsq": dict(routing="jsq", order="priority"),
    "R3b_priority_jsq_travel": dict(routing="jsq_travel", order="priority"),
}


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase3_regimes_{timestamp}.csv"
    out_path.parent.mkdir(exist_ok=True)

    t0 = time.time()
    rows = []
    for rho in RHO_VALUES:
        lam_total = rho * N * MU
        Lc_a = L_concentrated(rho, N, M)
        Ld_a = L_distributed(rho, M)
        for regime_name, kwargs in REGIMES.items():
            L_vals = []
            for seed in SEEDS:
                r = simulate_regime(n_stations=N, capacity=M, lam_total=lam_total,
                                     mu=MU, horizon=HORIZON, seed=seed,
                                     slack_mean=SLACK_MEAN, **kwargs)
                L_vals.append(r["L"])
                rows.append({
                    "rho": rho, "regime": regime_name, "seed": seed,
                    "L_sim": r["L"], "L_d_analytic": Ld_a, "L_c_analytic": Lc_a,
                    "block_frac": r["block_frac"], "within_window": r["within_window"],
                })
            mean_L = sum(L_vals) / len(L_vals)
            print(f"rho={rho:.1f} {regime_name:20s} mean_L={mean_L:.3f} "
                  f"(L_d_analytic={Ld_a:.3f}, L_c_analytic={Lc_a:.3f})")

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
