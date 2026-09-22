"""Shared statistics helpers: bootstrap CIs, paired significance tests, and
crossover-point estimation with CRN + bootstrap (Section 7 methodology:
>=30 seeds, 95% CIs, paired Wilcoxon, bootstrap for noisy crossover
estimates rather than plain bisection)."""

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.stats import wilcoxon


def bootstrap_ci(data, stat_fn=np.mean, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0):
    """Returns (point_estimate, ci_lo, ci_hi)."""
    rng = np.random.default_rng(seed)
    data = np.asarray(data)
    n = len(data)
    boot_stats = np.array([stat_fn(data[rng.integers(0, n, size=n)]) for _ in range(n_boot)])
    lo, hi = np.percentile(boot_stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(stat_fn(data)), float(lo), float(hi)


def paired_test(a, b):
    """Wilcoxon signed-rank test on paired samples (same seeds/CRN). Returns
    (statistic, p_value). Falls back to reporting a tie if all diffs are
    zero (wilcoxon raises in that degenerate case)."""
    a, b = np.asarray(a), np.asarray(b)
    diffs = a - b
    if np.all(diffs == 0):
        return 0.0, 1.0
    stat, p = wilcoxon(a, b)
    return float(stat), float(p)


def estimate_crossover_ci(rho_grid, values_a_by_rho, values_b_by_rho, n_boot: int = 2000,
                           seed: int = 0, method: str = "spline"):
    """values_a_by_rho, values_b_by_rho: dict rho -> list of per-seed values
    (same seeds across a/b at each rho -- CRN). Finds where mean(a)-mean(b)
    crosses zero, bootstrapping over seeds (resampling the seed index
    jointly for a and b at every rho, preserving CRN pairing) to get a CI
    on the crossover. Returns (point_estimate, ci_lo, ci_hi, bracket) or
    (None, None, None, None) if no sign change is found on the grid.

    method: 'spline' (default, REMEDIATION.md E2 fix) or 'linear' (the
    original method, kept for comparison/back-compat). E2: plain linear
    interpolation between the two bracketing grid points has measurable
    bias on a coarse rho grid -- measured directly on exact analytic
    inputs (no simulation noise at all) at 0.000173 (n=5,m=7, 6-point
    grid), 0.001812 (n=4,m=6, 5-point grid), 0.005799 (n=10,m=9, 5-point
    grid) -- i.e. bias grows with grid coarseness and function curvature,
    and was the actual cause of the earlier "CI misses the analytic value"
    observation at the two coarser-grid points, not simulation noise.
    Fitting a cubic spline through all grid points before root-finding
    (rather than a straight line through just the two bracketing points)
    must bring all three of those biases under 1e-3 -- see
    test_stats.py::test_crossover_ci_bias_on_analytic_inputs_meets_e2_threshold.
    """
    assert method in ("spline", "linear")
    rhos = sorted(rho_grid)
    n_seeds = len(values_a_by_rho[rhos[0]])
    rng = np.random.default_rng(seed)

    def find_crossing_linear(diffs_by_rho):
        for k in range(len(rhos) - 1):
            r0, r1 = rhos[k], rhos[k + 1]
            d0, d1 = diffs_by_rho[r0], diffs_by_rho[r1]
            if (d0 < 0) != (d1 < 0):
                frac = d0 / (d0 - d1)
                return r0 + frac * (r1 - r0)
        return None

    def find_crossing_spline(diffs_by_rho):
        d = np.array([diffs_by_rho[r] for r in rhos])
        if len(rhos) < 4:
            return find_crossing_linear(diffs_by_rho)  # cubic spline needs >=4 points
        spline = CubicSpline(rhos, d)
        dense_rho = np.linspace(rhos[0], rhos[-1], 20000)
        dense_d = spline(dense_rho)
        sign_changes = np.flatnonzero((dense_d[:-1] < 0) != (dense_d[1:] < 0))
        if len(sign_changes) == 0:
            return None
        k = sign_changes[0]
        r0, r1 = dense_rho[k], dense_rho[k + 1]
        d0, d1 = dense_d[k], dense_d[k + 1]
        frac = d0 / (d0 - d1)
        return r0 + frac * (r1 - r0)

    find_crossing = find_crossing_spline if method == "spline" else find_crossing_linear

    point_diffs = {r: np.mean(values_a_by_rho[r]) - np.mean(values_b_by_rho[r]) for r in rhos}
    point_estimate = find_crossing(point_diffs)
    if point_estimate is None:
        return None, None, None, None

    boot_estimates = []
    for _ in range(n_boot):
        idx = rng.integers(0, n_seeds, size=n_seeds)
        diffs = {r: np.mean(np.asarray(values_a_by_rho[r])[idx]) - np.mean(np.asarray(values_b_by_rho[r])[idx])
                  for r in rhos}
        c = find_crossing(diffs)
        if c is not None:
            boot_estimates.append(c)

    if not boot_estimates:
        return point_estimate, None, None, None
    lo, hi = np.percentile(boot_estimates, [2.5, 97.5])
    return point_estimate, float(lo), float(hi), (rhos[0], rhos[-1])
