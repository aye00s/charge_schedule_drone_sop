import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase1_baseline import L_concentrated, L_distributed, t_concentrated, t_distributed
from sim.core import simulate_mmnm


def test_output_ranges_valid():
    result = simulate_mmnm(lam=2.0, mu=1.0, n_servers=2, capacity=10, horizon=2000, seed=1)
    assert result["L"] >= 0
    assert result["wait"] >= 0
    assert 0 <= result["block_frac"] <= 1


def test_same_seed_is_deterministic():
    r1 = simulate_mmnm(lam=2.0, mu=1.0, n_servers=2, capacity=10, horizon=2000, seed=42)
    r2 = simulate_mmnm(lam=2.0, mu=1.0, n_servers=2, capacity=10, horizon=2000, seed=42)
    assert r1 == r2


def test_different_seeds_generally_differ():
    r1 = simulate_mmnm(lam=2.0, mu=1.0, n_servers=2, capacity=10, horizon=2000, seed=1)
    r2 = simulate_mmnm(lam=2.0, mu=1.0, n_servers=2, capacity=10, horizon=2000, seed=2)
    assert r1 != r2


def test_low_load_short_queue():
    # Very light load (rho << 1): system should rarely block and L should be small.
    result = simulate_mmnm(lam=0.1, mu=1.0, n_servers=1, capacity=10, horizon=5000, seed=7)
    assert result["L"] < 1.0
    assert result["block_frac"] < 0.05


def test_heavy_load_high_blocking():
    # Very heavy load (rho >> 1) into a small-capacity system: blocking should
    # dominate and the system should sit near full.
    result = simulate_mmnm(lam=20.0, mu=1.0, n_servers=1, capacity=5, horizon=5000, seed=7)
    assert result["block_frac"] > 0.5
    assert result["L"] > 3.0


# Fast regression check against Phase 1 analytics (short horizon, 2 seeds,
# averaged). A larger sweep (16 (n,m,rho) configs, 3 seeds, horizon=5e4) was
# run separately and gave a worst-case relative error of 3.5%; this test uses
# a 10% tolerance since the shorter horizon here is noisier by construction.
REL_TOL = 0.10


def _rel_err(sim_val, analytic_val):
    return abs(sim_val - analytic_val) / max(abs(analytic_val), 1e-9)


def test_simulator_matches_analytics():
    mu = 1.0
    horizon = 20000
    seeds = [1, 2]
    for n, m, rho in [(5, 7, 0.8), (5, 7, 1.2)]:
        lam_total = rho * n * mu
        Ld_sim, Lc_sim, td_sim, tc_sim = [], [], [], []
        for seed in seeds:
            d = simulate_mmnm(lam=lam_total / n, mu=mu, n_servers=1, capacity=m,
                               horizon=horizon, seed=seed)
            c = simulate_mmnm(lam=lam_total, mu=mu, n_servers=n, capacity=n * m,
                               horizon=horizon, seed=seed)
            Ld_sim.append(d["L"])
            Lc_sim.append(c["L"])
            td_sim.append(d["wait"] * lam_total)
            tc_sim.append(c["wait"] * lam_total)

        assert _rel_err(np.mean(Ld_sim), L_distributed(rho, m)) < REL_TOL
        assert _rel_err(np.mean(Lc_sim), L_concentrated(rho, n, m)) < REL_TOL
        assert _rel_err(np.mean(td_sim), t_distributed(rho, m, n)) < REL_TOL
        assert _rel_err(np.mean(tc_sim), t_concentrated(rho, n, m)) < REL_TOL
