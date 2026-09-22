"""Phase 1: analytical replication of Wang et al. (2020), Tables 2 and 3.

Reference: WANG Y Z, XU G N, WANG S, LI Z J, CAI R. "Optimization of charging
queuing of UAV swarming." Acta Aeronautica et Astronautica Sinica, 2020,
41(10): 323928. DOI: 10.7527/S1000-6893.2020.23928.
"""

import math

RHO_LIMIT = 1e-12


def L_distributed(rho: float, m: int) -> float:
    """Eq. 11: average queue length, distributed (n independent M/M/1/m queues)."""
    if abs(rho - 1) < RHO_LIMIT:
        return (m**2 - m) / (2 * (m + 1))
    return rho * ((m - 1) * rho ** (m + 1) - m * rho**m + rho) / ((1 - rho) * (1 - rho ** (m + 1)))


def P0_concentrated(rho: float, n: int, m: int) -> float:
    """Eq. 15: empty-system probability, concentrated (M/M/n/nm)."""
    nm = n * m
    if abs(rho - 1) < RHO_LIMIT:
        s = sum(n**k / math.factorial(k) for k in range(n))
        tail = (n**n / math.factorial(n)) * (nm - n + 1)
        return 1.0 / (s + tail)
    s = sum((n * rho) ** k / math.factorial(k) for k in range(n))
    tail = (n * rho) ** n / math.factorial(n) * (1 - rho ** (nm - n + 1)) / (1 - rho)
    return 1.0 / (s + tail)


def P_full_concentrated(rho: float, n: int, m: int) -> float:
    """Eq. 16: blocking probability at capacity nm, concentrated."""
    nm = n * m
    p0 = P0_concentrated(rho, n, m)
    return (n**n * rho**nm / math.factorial(n)) * p0


def L_concentrated(rho: float, n: int, m: int) -> float:
    """Eq. 13: average queue length, concentrated."""
    nm = n * m
    p0 = P0_concentrated(rho, n, m)
    if abs(rho - 1) < RHO_LIMIT:
        return (n**n / (2 * math.factorial(n))) * (nm - n) * (nm - n + 1) * p0
    factor = (n**n * rho ** (n + 1) * p0) / (math.factorial(n) * (1 - rho) ** 2)
    bracket = 1 - (nm - n + 1) * rho ** (nm - n) + (nm - n) * rho ** (nm - n + 1)
    return factor * bracket


def t_distributed(rho: float, m: int, n: int) -> float:
    """Eq. 18: average waiting time, distributed, with 1/lambda factored out."""
    if abs(rho - 1) < RHO_LIMIT:
        return n * (m - 1) / 2
    return n * rho * ((m - 1) * rho ** (m + 1) - m * rho**m + rho) / ((1 - rho) * (1 - rho**m))


def t_concentrated(rho: float, n: int, m: int) -> float:
    """Eq. 19: average waiting time, concentrated, with 1/lambda factored out."""
    nm = n * m
    p0 = P0_concentrated(rho, n, m)
    p_nm = P_full_concentrated(rho, n, m)
    if abs(rho - 1) < RHO_LIMIT:
        return (n**n * p0) / (2 * math.factorial(n) * (1 - p_nm)) * (nm - n) * (nm - n + 1)
    factor = (n**n * rho ** (n + 1) * p0) / (math.factorial(n) * (1 - rho) ** 2 * (1 - p_nm))
    bracket = 1 - (nm - n + 1) * rho ** (nm - n) + (nm - n) * rho ** (nm - n + 1)
    return factor * bracket


def bisect(f, lo: float, hi: float, tol: float = 1e-4, max_iter: int = 200) -> float:
    """Bisection on f, converging when the bracket width is below tol (matches
    the paper's stated bisection precision of 1e-4). Requires f(lo) and f(hi)
    to have opposite signs -- checked explicitly (not just assumed) because a
    bracket that doesn't actually contain a root converges silently to a
    wrong value with no error (this exact bug produced the wrong X1
    total-queue-crossover numbers, since the bracket reused for that call
    was a different metric's crossover window and never reached the real
    root)."""
    f_lo = f(lo)
    f_hi = f(hi)
    if (f_lo < 0) == (f_hi < 0):
        raise ValueError(f"bisect: f(lo)={f_lo} and f(hi)={f_hi} have the same sign -- "
                          f"bracket [{lo},{hi}] does not contain a root")
    for _ in range(max_iter):
        if hi - lo < tol:
            break
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if (f_lo < 0) == (f_mid < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


# Table 2 (queue-length crossover rho*), rows n=4..10, columns m=6,7,8,9
TABLE2 = {
    4: [0.70751953125, 0.73193359375, 0.75205078125, 0.76884765625],
    5: [0.72783203125, 0.75048828125, 0.76904296875, 0.78447265625],
    6: [0.74315703125, 0.76455078125, 0.78193859375, 0.79619140625],
    7: [0.75576171875, 0.77568359375, 0.79208984375, 0.80556640625],
    8: [0.76611328125, 0.78486328125, 0.80029249675, 0.81318359375],
    9: [0.77470703125, 0.79267578125, 0.80751953125, 0.81982421875],
    10: [0.78193359375, 0.79931640625, 0.81357421875, 0.82529296875],
}

# Table 3 (waiting-time crossover rho*), rows n=4..10, columns m=6,7,8,9
TABLE3 = {
    4: [1.019188720703125, 1.013821923828125, 1.010406689453125, 1.008089208984375],
    5: [1.014553759765625, 1.010406689453125, 1.007845263671875, 1.006137646484375],
    6: [1.011504443359375, 1.008211181640625, 1.006259619140625, 1.004795947265625],
    7: [1.009430908203125, 1.006747509765625, 1.005039892578125, 1.003942138671875],
    8: [1.007967236328125, 1.005649755859375, 1.004308056640625, 1.003332275390625],
    9: [1.006869482421875, 1.004917919921875, 1.003698193359375, 1.002844384765625],
    10: [1.006015673828125, 1.004308056640625, 1.003210302734375, 1.002478466796875],
}

M_VALUES = [6, 7, 8, 9]
N_VALUES = [4, 5, 6, 7, 8, 9, 10]


def validate_table2(bracket=(0.7, 0.9), tol=1e-9):
    """Recompute the queue-length crossover for every (n, m) and compare to Table 2."""
    results = {}
    for n in N_VALUES:
        row = []
        for m in M_VALUES:
            f = lambda rho, n=n, m=m: L_concentrated(rho, n, m) - L_distributed(rho, m)
            rho_star = bisect(f, *bracket, tol=tol)
            row.append(rho_star)
        results[n] = row
    max_dev = max(
        abs(results[n][j] - TABLE2[n][j]) for n in N_VALUES for j in range(len(M_VALUES))
    )
    return results, max_dev


def validate_table3(bracket=(1.0001, 1.125), tol=1e-9):
    """Recompute the waiting-time crossover for every (n, m) and compare to Table 3."""
    results = {}
    for n in N_VALUES:
        row = []
        for m in M_VALUES:
            f = lambda rho, n=n, m=m: t_concentrated(rho, n, m) - t_distributed(rho, m, n)
            rho_star = bisect(f, *bracket, tol=tol)
            row.append(rho_star)
        results[n] = row
    max_dev = max(
        abs(results[n][j] - TABLE3[n][j]) for n in N_VALUES for j in range(len(M_VALUES))
    )
    return results, max_dev


if __name__ == "__main__":
    _, dev2 = validate_table2()
    _, dev3 = validate_table3()
    print(f"Table 2 max deviation: {dev2:.6e}")
    print(f"Table 3 max deviation: {dev3:.6e}")
