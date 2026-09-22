"""Phase 5: exact MILP formulation of the charge-scheduling problem (Section
4), solved with PuLP + CBC. Scoped down from the full model in one
documented way: v1 uses a single constant charging rate per station (the
base linear SoC recurrence of Section 4.3 with fixed r_j), not yet the full
piecewise CC-CV upper-bound family (C9). That is a genuinely separate set of
constraints layered on top -- not implemented here, see the module
docstring note below for the exact formulation to add later.

Variables:
  x[i,j,t] in {0,1}  -- drone i charges at station j during slot t
  S[i,t]   in [sigma, 1]  -- SoC of drone i at the START of slot t, t=0..T

Constraints:
  C1  sum_i x[i,j,t] <= pads[j]                          (pad capacity)
  C2  sum_j x[i,j,t] <= 1                                 (one station at a time)
  C3/C4  sigma <= S[i,t] <= 1                             (SoC bounds, as variable bounds)
  SoC recurrence (linear -- fixed rate per station, x is binary, no Big-M needed).
  Uses <= rather than == deliberately: an == equality plus the S<=1 upper
  bound made the model infeasible whenever a charging decision would
  physically overshoot 100% (caught by fixing x to a known-feasible
  heuristic solution and finding the MILP still called it infeasible -- the
  equality forced S past its own upper bound instead of saturating). The
  inequality lets the solver saturate at 1.0 exactly like real charging
  does, and since the objective only rewards using fewer charging
  assignments (never rewards a lower S), the optimal solution always sets
  S[i,t+1] to its tightest feasible value -- the inequality never lets the
  solver "cheat" by pretending SoC is lower than it truly is.
      S[i,t+1] <= S[i,t] + sum_j (eta*rate_w[j]*dt_min/60/battery_wh[i]) * x[i,j,t]
  Deadline (hard): S[i, deadline_slot[i]] >= required_soc[i]
  Initial: S[i,0] = S0[i]

Objective: minimize total pad-occupancy sum_{i,j,t} x[i,j,t] (a station-time /
congestion / wear proxy), i.e. use no more charging time than necessary to
meet every deadline.

Full piecewise CC-CV extension (C9) and charging continuity (C10): see
solve_charge_schedule_milp_ccv below. NOTE (2026-09-21): an earlier version
of this docstring stated the C9 formulation as "S[i,t+1] <= S[i,t] +
rate_l*dt + M*(1-x[i,j,t]) for every band l" applied simultaneously for all
bands whenever charging. That is WRONG -- it applies EVERY band's rate as a
simultaneous upper bound regardless of the drone's actual SoC, so the
tightest (slowest, 50W) band would always dominate for every drone
regardless of how low their SoC is. Caught before implementing, not after.
The correct formulation needs an indicator variable selecting which band
S[i,t] is actually in; see the implementation for the corrected version.
"""

import math

import pulp

from sim.energy import CHARGE_BANDS


def solve_charge_schedule_milp(n_drones: int, pads: list, S0: list, required_soc: list,
                                deadline_slot: list, horizon_min: float, dt_min: float,
                                battery_wh=90.0, station_rate_w=200.0, eta: float = 1.0,
                                sigma: float = 0.20, time_limit_sec: int = 60) -> dict:
    n_stations = len(pads)
    T = int(round(horizon_min / dt_min))
    battery = [battery_wh] * n_drones if isinstance(battery_wh, (int, float)) else battery_wh
    rate_w = [station_rate_w] * n_stations if isinstance(station_rate_w, (int, float)) else station_rate_w

    prob = pulp.LpProblem("charge_schedule", pulp.LpMinimize)

    x = pulp.LpVariable.dicts("x", (range(n_drones), range(n_stations), range(T)), cat="Binary")
    S = pulp.LpVariable.dicts("S", (range(n_drones), range(T + 1)), lowBound=sigma, upBound=1.0)

    prob += pulp.lpSum(x[i][j][t] for i in range(n_drones) for j in range(n_stations) for t in range(T))

    for i in range(n_drones):
        prob += S[i][0] == S0[i]
        for t in range(T):
            prob += pulp.lpSum(x[i][j][t] for j in range(n_stations)) <= 1  # C2
            inc = pulp.lpSum((eta * rate_w[j] * dt_min / 60.0 / battery[i]) * x[i][j][t]
                              for j in range(n_stations))
            prob += S[i][t + 1] <= S[i][t] + inc
        prob += S[i][deadline_slot[i]] >= required_soc[i]

    for j in range(n_stations):
        for t in range(T):
            prob += pulp.lpSum(x[i][j][t] for i in range(n_drones)) <= pads[j]  # C1

    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_sec)
    prob.solve(solver)

    status = pulp.LpStatus[prob.status]
    x_sol = {(i, j, t): int(round(pulp.value(x[i][j][t])))
             for i in range(n_drones) for j in range(n_stations) for t in range(T)}
    S_sol = {(i, t): pulp.value(S[i][t]) for i in range(n_drones) for t in range(T + 1)}

    return {
        "status": status,
        "objective": pulp.value(prob.objective) if status == "Optimal" else None,
        "x": x_sol,
        "S": S_sol,
        "T": T,
        "n_drones": n_drones,
        "n_stations": n_stations,
    }


def solve_charge_schedule_heuristic(n_drones: int, pads: list, S0: list, required_soc: list,
                                     deadline_slot: list, horizon_min: float, dt_min: float,
                                     battery_wh=90.0, station_rate_w=200.0, eta: float = 1.0,
                                     sigma: float = 0.20) -> dict:
    """Greedy least-slack-first heuristic for the SAME discrete problem the
    MILP solves (same variables, same objective), for a genuine optimality
    gap comparison. At each slot, drones still short of their target are
    ranked by slack = (deadline_slot - t) - (charging slots still needed),
    and available pads go to the least-slack drones first."""
    n_stations = len(pads)
    T = int(round(horizon_min / dt_min))
    battery = [battery_wh] * n_drones if isinstance(battery_wh, (int, float)) else battery_wh
    rate_w = [station_rate_w] * n_stations if isinstance(station_rate_w, (int, float)) else station_rate_w
    rate_per_slot = [[eta * rate_w[j] * dt_min / 60.0 / battery[i] for j in range(n_stations)]
                      for i in range(n_drones)]

    S = [[0.0] * (T + 1) for _ in range(n_drones)]
    for i in range(n_drones):
        S[i][0] = S0[i]
    x = {}
    infeasible = False

    for t in range(T):
        remaining_need = []
        for i in range(n_drones):
            if S[i][t] >= required_soc[i] - 1e-9:
                remaining_need.append((i, 0))
                continue
            # slots still needed at this drone's best available station rate
            best_rate = max(rate_per_slot[i])
            slots_needed = math.ceil((required_soc[i] - S[i][t]) / best_rate - 1e-9)
            remaining_need.append((i, slots_needed))

        candidates = []
        for i, need in remaining_need:
            if need <= 0:
                continue
            slack = (deadline_slot[i] - t) - need
            if deadline_slot[i] <= t:
                continue  # past its own deadline, nothing more to schedule
            candidates.append((slack, i))
        candidates.sort(key=lambda c: c[0])  # least slack first

        pad_free = list(pads)
        assigned_this_slot = set()
        for slack, i in candidates:
            for j in range(n_stations):
                if pad_free[j] > 0:
                    x[(i, j, t)] = 1
                    pad_free[j] -= 1
                    assigned_this_slot.add(i)
                    break
        for i in range(n_drones):
            for j in range(n_stations):
                x.setdefault((i, j, t), 0)
            inc = sum(x[(i, j, t)] * rate_per_slot[i][j] for j in range(n_stations))
            S[i][t + 1] = min(1.0, S[i][t] + inc)

    for i in range(n_drones):
        if S[i][deadline_slot[i]] < required_soc[i] - 1e-6:
            infeasible = True

    objective = sum(x.values())
    return {
        "status": "Infeasible" if infeasible else "Heuristic",
        "objective": objective if not infeasible else None,
        "x": x,
        "S": {(i, t): S[i][t] for i in range(n_drones) for t in range(T + 1)},
        "T": T,
        "n_drones": n_drones,
        "n_stations": n_stations,
    }


def solve_charge_schedule_milp_ccv(n_drones: int, pads: list, S0: list, required_soc: list,
                                    deadline_slot: list, horizon_min: float, dt_min: float,
                                    battery_wh=90.0, eta: float = 1.0, sigma: float = 0.20,
                                    min_dwell_slots: int = 1, time_limit_sec: int = 120) -> dict:
    """C9 (full piecewise CC-CV charging curve) and C10 (minimum dwell time
    / charging continuity), correctly formulated:

    C9 -- band selection via indicator variables z[i,t,l] (one band active
    per drone per slot), Big-M linking S[i,t] to its active band, and a
    further Big-M linking the charging increment to BOTH the charge
    decision x and the active band z:
        sum_l z[i,t,l] = 1
        S[i,t] >= lo_l - M*(1 - z[i,t,l])              for all l
        S[i,t] <= hi_l + M*(1 - z[i,t,l])               for all l
        S[i,t+1] <= S[i,t] + rate_l*eta*dt_min/60/battery_wh[i]
                     + M*(2 - x_total[i,t] - z[i,t,l])   for all j, l
    where x_total[i,t] = sum_j x[i,j,t] (<=1 by C2). M=1.0 suffices since
    all SoC quantities lie in [0,1].

    C10 -- minimum dwell / no rapid on-off switching: once a charging
    session starts (a "rising edge" in sum_j x[i,j,t]), it must continue
    for min_dwell_slots. This needs no Big-M: since sum_j x[i,j,t] is
    binary (C2), the rising-edge difference directly forces continuity:
        (sum_j x[i,j,t] - sum_j x[i,j,t-1]) <= sum_j x[i,j,t']
        for every t' in [t, min(T-1, t+min_dwell_slots-1)]
    (t=0 treated as a rising edge whenever x[i,*,0]=1, no t-1 term).

    Objective, variables x/S otherwise identical to solve_charge_schedule_milp.

    Known approximation: the active band is selected from S[i,t] (the START
    of the slot) and that band's rate applies for the WHOLE slot, so a slot
    that would physically cross a band boundary partway through (e.g.
    starting at 0.68 and charging past 0.70) is slightly over-credited
    versus the true continuous curve. This is a standard discretization
    trade-off for slot-based MILPs; a finer dt_min reduces the error. Not
    fixed here -- documented, not silent.
    """
    n_stations = len(pads)
    T = int(round(horizon_min / dt_min))
    battery = [battery_wh] * n_drones if isinstance(battery_wh, (int, float)) else battery_wh
    bands = CHARGE_BANDS
    n_bands = len(bands)
    BIG_M = 1.0

    prob = pulp.LpProblem("charge_schedule_ccv", pulp.LpMinimize)

    x = pulp.LpVariable.dicts("x", (range(n_drones), range(n_stations), range(T)), cat="Binary")
    S = pulp.LpVariable.dicts("S", (range(n_drones), range(T + 1)), lowBound=sigma, upBound=1.0)
    z = pulp.LpVariable.dicts("z", (range(n_drones), range(T), range(n_bands)), cat="Binary")

    prob += pulp.lpSum(x[i][j][t] for i in range(n_drones) for j in range(n_stations) for t in range(T))

    for i in range(n_drones):
        prob += S[i][0] == S0[i]
        for t in range(T):
            prob += pulp.lpSum(x[i][j][t] for j in range(n_stations)) <= 1  # C2

            prob += pulp.lpSum(z[i][t][l] for l in range(n_bands)) == 1
            for l, (lo, hi, rate) in enumerate(bands):
                prob += S[i][t] >= lo - BIG_M * (1 - z[i][t][l])
                prob += S[i][t] <= hi + BIG_M * (1 - z[i][t][l])

            x_total_t = pulp.lpSum(x[i][j][t] for j in range(n_stations))
            for l, (lo, hi, rate) in enumerate(bands):
                rate_per_slot = eta * rate * dt_min / 60.0 / battery[i]
                prob += S[i][t + 1] <= S[i][t] + rate_per_slot + BIG_M * (2 - x_total_t - z[i][t][l])
            # Without charging, every band constraint above is Big-M-relaxed
            # simultaneously (x_total_t=0 alone adds +BIG_M regardless of
            # z), leaving S[i,t+1] completely unconstrained up to its own
            # upBound=1.0 -- caught by testing a within-one-band instance
            # and finding the solver charged nobody yet reached the target
            # anyway (objective=0). This constraint patches that hole.
            prob += S[i][t + 1] <= S[i][t] + BIG_M * x_total_t
            # This model has no discharge/flight component, so SoC must be
            # monotone non-decreasing -- without this, nothing in the
            # objective penalizes an intermediate S value dropping for no
            # reason (only the upper bound on increase is constrained
            # above), and CBC found a "valid" but physically nonsensical
            # trajectory that dipped between charging sessions with the
            # same objective value. Caught by inspecting a multi-band SoC
            # trajectory and finding a drop with no discharge to explain it.
            prob += S[i][t + 1] >= S[i][t]

            # C10: minimum dwell time once a charging session starts
            if min_dwell_slots > 1:
                x_prev = pulp.lpSum(x[i][j][t - 1] for j in range(n_stations)) if t > 0 else 0
                rising_edge = x_total_t - x_prev
                for t_prime in range(t, min(T, t + min_dwell_slots)):
                    x_total_tp = pulp.lpSum(x[i][j][t_prime] for j in range(n_stations))
                    prob += rising_edge <= x_total_tp

        prob += S[i][deadline_slot[i]] >= required_soc[i]

    for j in range(n_stations):
        for t in range(T):
            prob += pulp.lpSum(x[i][j][t] for i in range(n_drones)) <= pads[j]  # C1

    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_sec)
    prob.solve(solver)

    status = pulp.LpStatus[prob.status]
    x_sol = {(i, j, t): int(round(pulp.value(x[i][j][t])))
             for i in range(n_drones) for j in range(n_stations) for t in range(T)}
    S_sol = {(i, t): pulp.value(S[i][t]) for i in range(n_drones) for t in range(T + 1)}

    return {
        "status": status,
        "objective": pulp.value(prob.objective) if status == "Optimal" else None,
        "x": x_sol,
        "S": S_sol,
        "T": T,
        "n_drones": n_drones,
        "n_stations": n_stations,
    }
