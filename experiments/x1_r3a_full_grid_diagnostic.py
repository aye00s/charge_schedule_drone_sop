"""Diagnostic (user-requested): full rho grid 0.2-1.6 for R3a vs
concentrated on per-drone wait t, with blocking reported alongside, to
find exactly where/why R3a appears to beat the theoretically-optimal
pooled baseline -- since a pooled M/M/n queue cannot be beaten on mean
wait by any routing to separate queues (verified at rho=0.5 via a
dedicated sanity test), any apparent R3a win must come from blocking-rate
divergence making "wait of admitted-only" a non-comparable quantity
between the two systems, not a real advantage. This run is diagnostic,
not a final-rigor statistical claim: 15 seeds, horizon=30,000.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase1_baseline import L_concentrated, t_concentrated
from sim.scheduler import simulate_regime

MU = 1.0
HORIZON = 30_000
SEEDS = list(range(1, 16))
SLACK_MEAN = 1.0 / MU
N, M = 5, 7
RHO_VALUES = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6]


def main():
    t0 = time.time()
    rows = []
    for rho in RHO_VALUES:
        lam_total = rho * N * MU
        tc_a = t_concentrated(rho, N, M)
        Lc_a = L_concentrated(rho, N, M)
        r3a_t, r3a_L, r3a_block = [], [], []
        r1_t, r1_block = [], []
        for seed in SEEDS:
            r3a = simulate_regime(routing="jsq", order="priority", n_stations=N, capacity=M,
                                   lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                   slack_mean=SLACK_MEAN)
            r1 = simulate_regime(routing="fixed_split", order="fcfs", n_stations=N, capacity=M,
                                  lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                  slack_mean=SLACK_MEAN)
            r3a_t.append(r3a["wait"] * lam_total)
            r3a_L.append(r3a["L"])
            r3a_block.append(r3a["block_frac"])
            r1_t.append(r1["wait"] * lam_total)
            r1_block.append(r1["block_frac"])
            rows.append({"rho": rho, "seed": seed, "t_r3a": r3a["wait"] * lam_total,
                        "L_r3a": r3a["L"], "block_r3a": r3a["block_frac"],
                        "t_r1": r1["wait"] * lam_total, "block_r1": r1["block_frac"],
                        "t_c_analytic": tc_a, "L_c_analytic": Lc_a})
        beats = np.mean(r3a_t) < tc_a
        print(f"rho={rho:.1f}  R3a: t={np.mean(r3a_t):7.3f} L={np.mean(r3a_L):6.3f} block={np.mean(r3a_block):.4f}  "
              f"|  R1: t={np.mean(r1_t):7.3f} block={np.mean(r1_block):.4f}  "
              f"|  t_c_analytic={tc_a:8.3f} block_c_implied={'n/a'}  "
              f"|  R3a {'BEATS' if beats else 'loses to'} concentrated on t "
              f"{'*** SUSPICIOUS ***' if beats else ''}", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x1_r3a_diagnostic_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
