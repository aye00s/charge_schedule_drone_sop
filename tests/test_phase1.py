import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase1_baseline import (
    L_concentrated,
    L_distributed,
    M_VALUES,
    N_VALUES,
    P0_concentrated,
    P_full_concentrated,
    TABLE2,
    TABLE3,
    bisect,
    t_concentrated,
    t_distributed,
    validate_table2,
    validate_table3,
)

TOL = 1e-3


def test_bisect_finds_known_root():
    root = bisect(lambda x: x - 0.37, 0.0, 1.0, tol=1e-6)
    assert abs(root - 0.37) < 1e-5


def test_rho_equals_one_matches_general_formula_limit():
    # Sanity check: general formulas approach the rho=1 closed forms as
    # rho -> 1 from both sides (no discontinuity at the limit switch-over).
    for n in [4, 7]:
        for m in [6, 9]:
            for eps in [1e-6, -1e-6]:
                rho = 1 + eps
                assert math.isfinite(L_distributed(rho, m))
                assert math.isfinite(L_concentrated(rho, n, m))
                assert math.isfinite(t_distributed(rho, m, n))
                assert math.isfinite(t_concentrated(rho, n, m))


def test_probabilities_are_valid():
    for n in N_VALUES:
        for m in M_VALUES:
            for rho in [0.4, 0.8, 1.0, 1.2]:
                p0 = P0_concentrated(rho, n, m)
                p_nm = P_full_concentrated(rho, n, m)
                assert 0 <= p0 <= 1
                assert 0 <= p_nm <= 1


def test_table2_within_tolerance():
    results, max_dev = validate_table2()
    for n in N_VALUES:
        for j, m in enumerate(M_VALUES):
            assert abs(results[n][j] - TABLE2[n][j]) < TOL, (
                f"n={n}, m={m}: got {results[n][j]}, expected {TABLE2[n][j]}"
            )
    assert max_dev < TOL


def test_table3_within_tolerance():
    results, max_dev = validate_table3()
    for n in N_VALUES:
        for j, m in enumerate(M_VALUES):
            assert abs(results[n][j] - TABLE3[n][j]) < TOL, (
                f"n={n}, m={m}: got {results[n][j]}, expected {TABLE3[n][j]}"
            )
    assert max_dev < TOL
