import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim.stats import bootstrap_ci, estimate_crossover_ci, paired_test


def test_bootstrap_ci_contains_true_mean_for_known_distribution():
    rng = np.random.default_rng(0)
    data = rng.normal(loc=10.0, scale=1.0, size=200)
    point, lo, hi = bootstrap_ci(data, seed=1)
    assert lo < point < hi
    assert abs(point - 10.0) < 0.5
    assert lo < 10.0 < hi


def test_paired_test_detects_consistent_difference():
    rng = np.random.default_rng(0)
    a = rng.normal(10, 1, 30)
    b = a + 2.0  # b consistently larger
    stat, p = paired_test(a, b)
    assert p < 0.01


def test_paired_test_no_difference_gives_high_p():
    rng = np.random.default_rng(0)
    a = rng.normal(10, 1, 30)
    b = rng.normal(10, 1, 30)
    stat, p = paired_test(a, b)
    assert p > 0.01  # not guaranteed but should usually hold for iid same-dist samples


def test_crossover_ci_finds_known_linear_crossing():
    # a-b = rho - 0.7 exactly (no noise) -> crossing at rho=0.7
    rhos = [0.5, 0.6, 0.7, 0.8, 0.9]
    a_by_rho = {r: [r] * 10 for r in rhos}
    b_by_rho = {r: [0.7] * 10 for r in rhos}
    point, lo, hi, bracket = estimate_crossover_ci(rhos, a_by_rho, b_by_rho, n_boot=200, method="linear")
    assert abs(point - 0.7) < 1e-9
    assert lo == hi == point  # no noise -> zero-width CI


def test_crossover_ci_bias_on_analytic_inputs_meets_e2_threshold():
    """E2: the estimator's bias on EXACT analytic inputs (no simulation
    noise at all) must be < 0.001 on the coarse rho grids actually used in
    the Phase 3 crossover experiments. Plain linear interpolation between
    the two bracketing grid points failed this (measured bias up to
    0.0058 at n=10,m=9's 5-point grid) -- this was the actual cause of the
    earlier "simulated CI misses the analytic crossover" observation, not
    simulation noise. The default 'spline' method (cubic spline through
    all grid points, not just the two bracketing ones) must pass."""
    from phase1_baseline import L_concentrated, L_distributed, bisect

    def true_crossover(n, m, bracket):
        f = lambda rho: L_distributed(rho, m) - L_concentrated(rho, n, m)
        return bisect(f, bracket[0], bracket[1], tol=1e-9)

    configs = [
        (5, 7, [0.55, 0.60, 0.65, 0.70, 0.75, 0.80], (0.55, 0.80)),
        (4, 6, [0.55, 0.60, 0.65, 0.70, 0.75], (0.55, 0.75)),
        (10, 9, [0.70, 0.75, 0.80, 0.85, 0.90], (0.70, 0.90)),
    ]
    for n, m, rho_grid, bracket in configs:
        Ld_by_rho = {r: [L_distributed(r, m)] * 5 for r in rho_grid}
        Lc_by_rho = {r: [L_concentrated(r, n, m)] * 5 for r in rho_grid}
        point, _, _, _ = estimate_crossover_ci(rho_grid, Lc_by_rho, Ld_by_rho, n_boot=100, seed=1,
                                                method="spline")
        true_val = true_crossover(n, m, bracket)
        assert abs(point - true_val) < 1e-3, f"n={n},m={m}: bias {point-true_val} exceeds E2 threshold"
