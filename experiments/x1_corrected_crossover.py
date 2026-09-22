"""X1: corrected crossover experiment (REMEDIATION.md E1 + E2 fixes).

E1: per-drone waiting time t is the PRIMARY crossover metric (already
like-for-like, t_d = n*L_d/(1-P_block)), not raw queue length L. L-based
crossover is still reported, labelled "replication of the reference
metric" only. Total-queue crossover (n*L_d vs L_c, purely analytic) and
blocking probability are also reported.

E2: uses the bias-corrected (cubic-spline) estimator in sim/stats.py,
which reduced bias on exact analytic inputs to <0.001 on all three grids
(vs up to 0.0058 with plain linear interpolation).

Scope of this run: R1 (FCFS, fixed-split) and R3a (priority, JSQ) at the
grid corners+middle (n,m) = (4,6), (5,7), (10,9), 30 seeds. R1's routing
is unaffected by the E3 fix (fixed_split never tie-broke), but R3a's
routing changed (waiting-count -> in-system-count, E3), so its numbers
here supersede the pre-remediation run. R3b (needs >=5 station layouts)
and R4 (R3a+JIT, which needs a conceptual decision for the queue-only
model -- see the report) are NOT run here; flagged as remaining X1 work.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase1_baseline import L_concentrated, L_distributed, bisect, t_concentrated, t_distributed
from sim.scheduler import simulate_regime
from sim.stats import bootstrap_ci, estimate_crossover_ci, paired_test

MU = 1.0
HORIZON = 50_000
SEEDS = list(range(1, 31))
SLACK_MEAN = 1.0 / MU

CONFIGS = [
    (4, 6, [0.55, 0.60, 0.65, 0.70, 0.75]),
    (5, 7, [0.55, 0.60, 0.65, 0.70, 0.75, 0.80]),
    (10, 9, [0.70, 0.75, 0.80, 0.85, 0.90]),
]


def total_queue_crossover(n, m):
    """Analytic, no simulation needed: n*L_d (total distributed) vs L_c
    (whole hub). E1's secondary metric.

    Bug fixed here (found by the user, 2026-09-22): this used to take the
    per-drone-wait rho_grid's own bracket (~0.55-0.90 depending on config)
    as the search bracket, on the wrong assumption that the total-queue
    crossover sits near the same location as the L-crossover. It doesn't
    -- for all three grid configs it sits between rho=0.95 and 1.00, so
    that bracket never contained a root and bisect() (before it validated
    its inputs) silently returned a wrong number anchored to the wrong
    window. Scanning for the sign change directly avoids assuming where
    the crossover is."""
    f = lambda rho: n * L_distributed(rho, m) - L_concentrated(rho, n, m)
    scan = [0.50 + 0.01 * i for i in range(101)]  # 0.50 .. 1.50
    lo, hi = None, None
    prev_rho, prev_sign = None, None
    for rho in scan:
        sign = f(rho) < 0
        if prev_sign is not None and sign != prev_sign:
            lo, hi = prev_rho, rho
            break
        prev_rho, prev_sign = rho, sign
    if lo is None:
        raise ValueError(f"total_queue_crossover: no sign change found for n={n}, m={m} in [0.50,1.50]")
    return bisect(f, lo, hi, tol=1e-9)


def main():
    t0 = time.time()
    all_rows = []
    summary = []

    for n, m, rho_grid in CONFIGS:
        L_r1_by_rho, L_r3a_by_rho = {}, {}
        t_r1_by_rho, t_r3a_by_rho = {}, {}
        block_r1_by_rho, block_r3a_by_rho = {}, {}

        for rho in rho_grid:
            lam_total = rho * n * MU
            Lc_a = L_concentrated(rho, n, m)
            tc_a = t_concentrated(rho, n, m)
            r1_L, r1_t, r1_block = [], [], []
            r3a_L, r3a_t, r3a_block = [], [], []
            for seed in SEEDS:
                r1 = simulate_regime(routing="fixed_split", order="fcfs", n_stations=n, capacity=m,
                                      lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                      slack_mean=SLACK_MEAN)
                r3a = simulate_regime(routing="jsq", order="priority", n_stations=n, capacity=m,
                                       lam_total=lam_total, mu=MU, horizon=HORIZON, seed=seed,
                                       slack_mean=SLACK_MEAN)
                r1_L.append(r1["L"]); r1_t.append(r1["wait"] * lam_total); r1_block.append(r1["block_frac"])
                r3a_L.append(r3a["L"]); r3a_t.append(r3a["wait"] * lam_total); r3a_block.append(r3a["block_frac"])
                all_rows.append({"n": n, "m": m, "rho": rho, "seed": seed,
                                  "L_r1": r1["L"], "L_r3a": r3a["L"],
                                  "t_r1": r1["wait"] * lam_total, "t_r3a": r3a["wait"] * lam_total,
                                  "block_r1": r1["block_frac"], "block_r3a": r3a["block_frac"],
                                  "L_c_analytic": Lc_a, "t_c_analytic": tc_a})
            L_r1_by_rho[rho] = r1_L; L_r3a_by_rho[rho] = r3a_L
            t_r1_by_rho[rho] = r1_t; t_r3a_by_rho[rho] = r3a_t
            block_r1_by_rho[rho] = r1_block; block_r3a_by_rho[rho] = r3a_block
            print(f"n={n} m={m} rho={rho:.2f}  "
                  f"R1: L={np.mean(r1_L):.3f} t={np.mean(r1_t):.3f} block={np.mean(r1_block):.3f}  "
                  f"R3a: L={np.mean(r3a_L):.3f} t={np.mean(r3a_t):.3f} block={np.mean(r3a_block):.3f}",
                  flush=True)

        Lc_by_rho = {r: [L_concentrated(r, n, m)] * len(SEEDS) for r in rho_grid}
        tc_by_rho = {r: [t_concentrated(r, n, m)] * len(SEEDS) for r in rho_grid}

        # PRIMARY (E1): per-drone wait-time crossover
        r1_t_cross = estimate_crossover_ci(rho_grid, tc_by_rho, t_r1_by_rho, seed=2, method="spline")
        r3a_t_cross = estimate_crossover_ci(rho_grid, tc_by_rho, t_r3a_by_rho, seed=2, method="spline")
        # SECONDARY: L-based, "replication of the reference metric" only
        r1_L_cross = estimate_crossover_ci(rho_grid, Lc_by_rho, L_r1_by_rho, seed=2, method="spline")
        r3a_L_cross = estimate_crossover_ci(rho_grid, Lc_by_rho, L_r3a_by_rho, seed=2, method="spline")
        # Total-queue crossover (analytic, E1's other secondary metric)
        total_queue_rho_star = total_queue_crossover(n, m)

        print(f"\n--- n={n} m={m} crossover summary ---")
        print(f"PRIMARY (per-drone wait t): R1 rho*={r1_t_cross[0]}, CI=[{r1_t_cross[1]},{r1_t_cross[2]}]")
        print(f"                            R3a rho*={r3a_t_cross[0]}, CI=[{r3a_t_cross[1]},{r3a_t_cross[2]}]")
        print(f"replication-only (L, per-pad): R1 rho*={r1_L_cross[0]}, R3a rho*={r3a_L_cross[0]}")
        print(f"total-queue (n*L_d vs L_c, analytic): rho*={total_queue_rho_star:.6f}")
        print(f"blocking at rho=1.0-ish: R1={np.mean(block_r1_by_rho.get(rho_grid[-1],[0])):.3f} "
              f"R3a={np.mean(block_r3a_by_rho.get(rho_grid[-1],[0])):.3f}\n", flush=True)

        summary.append({
            "n": n, "m": m,
            "t_crossover_R1": r1_t_cross[0], "t_crossover_R1_lo": r1_t_cross[1], "t_crossover_R1_hi": r1_t_cross[2],
            "t_crossover_R3a": r3a_t_cross[0], "t_crossover_R3a_lo": r3a_t_cross[1], "t_crossover_R3a_hi": r3a_t_cross[2],
            "L_crossover_R1_replication_only": r1_L_cross[0],
            "L_crossover_R3a_replication_only": r3a_L_cross[0],
            "total_queue_crossover_analytic": total_queue_rho_star,
        })

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x1_corrected_crossover_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    summary_path = ROOT / "results" / f"x1_summary_{timestamp}.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)
    print(f"\nWrote {len(all_rows)} rows to {out_path}")
    print(f"Wrote summary to {summary_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
