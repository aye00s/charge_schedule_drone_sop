"""Phase 2 validation sweep: simulator vs analytics across the full (n, m)
grid used in the reference paper's tables, several rho points, multiple
seeds. Writes one row per run to a timestamped CSV under results/ (raw
results are never overwritten -- Section 11 convention).
"""

import csv
import datetime
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase1_baseline import L_concentrated, L_distributed, t_concentrated, t_distributed
from sim.core import simulate_mmnm

MU = 1.0
HORIZON = 100_000
SEEDS = [1, 2, 3]
N_VALUES = [4, 5, 6, 7, 8, 9, 10]
M_VALUES = [6, 7, 8, 9]
RHO_VALUES = [0.6, 0.8, 1.0, 1.2]


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase2_validation_{timestamp}.csv"
    out_path.parent.mkdir(exist_ok=True)

    t0 = time.time()
    rows = []
    for n in N_VALUES:
        for m in M_VALUES:
            for rho in RHO_VALUES:
                lam_total = rho * n * MU
                for seed in SEEDS:
                    d = simulate_mmnm(lam=lam_total / n, mu=MU, n_servers=1,
                                       capacity=m, horizon=HORIZON, seed=seed)
                    c = simulate_mmnm(lam=lam_total, mu=MU, n_servers=n,
                                       capacity=n * m, horizon=HORIZON, seed=seed)
                    Ld_a = L_distributed(rho, m)
                    Lc_a = L_concentrated(rho, n, m)
                    td_a = t_distributed(rho, m, n)
                    tc_a = t_concentrated(rho, n, m)
                    td_s = d["wait"] * lam_total
                    tc_s = c["wait"] * lam_total
                    rows.append({
                        "n": n, "m": m, "rho": rho, "seed": seed, "horizon": HORIZON,
                        "L_d_analytic": Ld_a, "L_d_sim": d["L"],
                        "L_c_analytic": Lc_a, "L_c_sim": c["L"],
                        "t_d_analytic": td_a, "t_d_sim": td_s,
                        "t_c_analytic": tc_a, "t_c_sim": tc_s,
                        "block_d": d["block_frac"], "block_c": c["block_frac"],
                    })
        print(f"n={n} done, elapsed={time.time()-t0:.1f}s", flush=True)

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    def rel_err(sim_v, a_v):
        return abs(sim_v - a_v) / max(abs(a_v), 1e-9)

    worst = {"L_d": 0.0, "L_c": 0.0, "t_d": 0.0, "t_c": 0.0}
    for r in rows:
        worst["L_d"] = max(worst["L_d"], rel_err(r["L_d_sim"], r["L_d_analytic"]))
        worst["L_c"] = max(worst["L_c"], rel_err(r["L_c_sim"], r["L_c_analytic"]))
        worst["t_d"] = max(worst["t_d"], rel_err(r["t_d_sim"], r["t_d_analytic"]))
        worst["t_c"] = max(worst["t_c"], rel_err(r["t_c_sim"], r["t_c_analytic"]))

    elapsed = time.time() - t0
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Total elapsed: {elapsed:.1f}s")
    print(f"Worst relative error: L_d={worst['L_d']:.1%} L_c={worst['L_c']:.1%} "
          f"t_d={worst['t_d']:.1%} t_c={worst['t_c']:.1%}")


if __name__ == "__main__":
    main()
