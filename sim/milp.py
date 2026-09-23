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

E8 fix (2026-09-23, REMEDIATION.md checkpoint 7): solve_charge_schedule_
milp_ccv's C9 used to apply the STARTING band's rate for the whole slot,
letting a slot cross past its own band's ceiling by more than the band is
wide. f13_pieces_for_band (F13) replaces that single increment with the
exact within-slot curve, verified to machine precision against
soc_after_charging. E9 (dwell-window truncation) was found ALREADY correct
on inspection -- see test_milp_v2.py::test_E9_dwell_window_already_
truncated_at_horizon, made permanent rather than left unverified.

MILP v2 (solve_charge_schedule_milp_v2) and its matching heuristic
(solve_charge_schedule_ours_v2) implement REMEDIATION.md Section 4: the
real F12 objective (alpha*C_max + beta*energy_cost + gamma*sum T_k),
replacing v1's constant pad-slot-count objective that made a 0% gap
structurally guaranteed rather than a property of heuristic quality (E10).
"""

import math

import numpy as np
import pulp

from sim.energy import CHARGE_BANDS


def f13_pieces_for_band(band_idx: int, dt_min: float, battery_wh: float, eta: float = 1.0) -> list:
    """F13 (REMEDIATION.md Section 2, fixes E8): for a drone starting a slot
    at SoC S within band `band_idx`, the exact SoC reached after `dt_min`
    minutes of charging, Phi(S), is piecewise-linear and CONCAVE in S --
    the pointwise minimum of one affine "regime" line per number of full
    band-boundaries crossed before dt_min runs out:
      regime 0 (never leaves the starting band): line(S) = S + rate_l*dt/60/B
      regime m>=1 (crosses m full boundaries, l -> l+1 -> ... -> l+m,
      finishing inside band l+m): affine in S with slope rate_{l+m}/rate_l,
      matching F13's stated slope sequence exactly.
    Returns a list of (a, b) so that Phi(S) = min_k(a_k*S + b_k) --
    verified numerically against soc_after_charging on a fine grid (see
    test_milp_v2.py) rather than trusted from the symbolic derivation
    alone, matching this project's own standing practice."""
    bands = CHARGE_BANDS
    n_bands = len(bands)
    lo_l, hi_l, rate_l = bands[band_idx]
    pieces = []
    # regime 0: stay in the starting band for the whole slot
    pieces.append((1.0, eta * rate_l * dt_min / 60.0 / battery_wh))
    # regime m >= 1: cross m full boundaries (bands l..l+m-1 fully
    # traversed), land partway into band l+m (capped at the top band if dt
    # outlasts every remaining band, matching soc_after_charging's own
    # min(s, 1.0) saturation). const_cross_min accumulates the CONSTANT
    # (S-independent) crossing time of every fully-crossed band strictly
    # after the starting band l -- band l's own crossing time is the one
    # S-dependent term, folded into the line algebraically below.
    const_cross_min = 0.0
    for m in range(1, n_bands - band_idx):
        target_band = min(band_idx + m, n_bands - 1)
        lo_t, hi_t, rate_t = bands[target_band]
        # remaining(S) = dt - [(hi_l - S)*B/(eta*rate_l)*60 + const_cross_min]
        #              = [dt - const_cross_min - hi_l*B/(eta*rate_l)*60] + S*B/(eta*rate_l)*60
        # line(S) = lo_t + eta*rate_t/60/B * remaining(S)
        a = rate_t / rate_l  # simplifies algebraically from the S-coefficient above
        intercept_of_remaining = dt_min - const_cross_min - hi_l * battery_wh / (eta * rate_l) * 60.0
        b = lo_t + (eta * rate_t / 60.0 / battery_wh) * intercept_of_remaining
        pieces.append((a, b))
        # band (band_idx+m) becomes fully crossed once we move to regime m+1
        if band_idx + m < n_bands - 1:
            lo_next, hi_next, rate_next = bands[band_idx + m]
            const_cross_min += (hi_next - lo_next) * battery_wh / (eta * rate_next) * 60.0
    # Saturation cap: soc_after_charging saturates at 1.0 (min(s, 1.0)), but
    # the highest-m regime line above (whose target_band is capped at the
    # top band once dt outlasts every remaining band) still assumes the top
    # band's rate applies indefinitely past S=1.0 -- an explicit constant
    # piece enforces the same cap here. Harmless for every other piece
    # (1.0 is always a valid, usually-loose upper bound on SoC).
    pieces.append((0.0, 1.0))
    return pieces


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
    per drone per slot), Big-M linking S[i,t] to its active band, and F13's
    exact within-slot curve (f13_pieces_for_band) for the charging
    increment -- see that function's docstring and the E8 note in this
    module's own docstring above.

    C10 -- minimum dwell / no rapid on-off switching: once a charging
    session starts (a "rising edge" in sum_j x[i,j,t]), it must continue
    for min_dwell_slots. This needs no Big-M: since sum_j x[i,j,t] is
    binary (C2), the rising-edge difference directly forces continuity:
        (sum_j x[i,j,t] - sum_j x[i,j,t-1]) <= sum_j x[i,j,t']
        for every t' in [t, min(T-1, t+min_dwell_slots-1)]
    (t=0 treated as a rising edge whenever x[i,*,0]=1, no t-1 term). The
    range's own min(T, ...) bound already truncates correctly at the
    horizon end (E9's own criterion) -- verified in test_milp_v2.py rather
    than assumed.

    Objective, variables x/S otherwise identical to solve_charge_schedule_milp.
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
            # E8/F13 fix (2026-09-23): a single rate_per_slot here used to
            # apply the STARTING band's rate for the whole slot even when
            # the slot's charging genuinely crosses into a slower band
            # partway through (verified: with dt_min=10, battery=90, a slot
            # starting at 69% added ~37% SoC -- past the band's own 70%
            # ceiling, unphysical). F13's per-band multi-piece formulation
            # (f13_pieces_for_band, verified exact against soc_after_charging
            # to machine precision) replaces the single increment with the
            # true within-slot curve, one <= constraint per piece.
            for l, (lo, hi, rate) in enumerate(bands):
                for a_coef, b_coef in f13_pieces_for_band(l, dt_min, battery[i], eta):
                    prob += S[i][t + 1] <= a_coef * S[i][t] + b_coef + BIG_M * (2 - x_total_t - z[i][t][l])
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


def solve_charge_schedule_milp_v2(n_drones: int, pads: list, S0: list, missions: list,
                                   battery_wh=90.0, eta: float = 1.0, sigma: float = 0.20,
                                   horizon_min: float = 360.0, dt_min: float = 10.0,
                                   alpha: float = 1.0, beta: float = 1.0, gamma: float = 1.0,
                                   tariff_flat: float = 0.15, min_dwell_slots: int = 1,
                                   time_limit_sec: int = 120) -> dict:
    """MILP v2 (REMEDIATION.md Section 4): the real F12 objective (Section
    2's raw form, alpha*C_max + beta*energy_cost($) + gamma*sum T_k, NOT
    mission_sim.py's normalized reporting variant), replacing v1's constant
    pad-slot-count objective (E10: v1's 0% gap is a property of that
    constant objective, not of the heuristic's optimality -- see the v1-
    vs-v2 side-by-side comparison in experiments/x7_milp_v2_gap.py).

    Depot simplification (stated here as in the paper): stations are at a
    depot; missions start and end at the depot. Each mission k is
    {duration_slots: D_k, energy_wh: e_k (already includes travel),
    release_slot, deadline_min}. C9 (F13, exact within-slot CC-CV) and C10
    (E9-fixed dwell truncation) reuse the same z[i,t,l] band-indicator
    machinery as solve_charge_schedule_milp_ccv.

    Known degeneracy (documented, not eliminated -- matches this project's
    own precedent for tied-optima artifacts elsewhere in this file): only
    the ACTUAL SoC increase is costed (not x itself), so the solver may set
    x[i,j,t]=1 without using the pad (S[i,t+1]=S[i,t]) when doing so costs
    nothing -- harmless to Z's value (and to the C1 capacity check, which
    still counts x[i,j,t]=1 as occupying a pad either way), but means x's
    0/1 pattern alone is not always a literal "did it charge" indicator.
    """
    n_stations = len(pads)
    T = int(round(horizon_min / dt_min))
    battery = [battery_wh] * n_drones if isinstance(battery_wh, (int, float)) else battery_wh
    bands = CHARGE_BANDS
    n_bands = len(bands)
    BIG_M = 1.0
    K = len(missions)

    prob = pulp.LpProblem("charge_schedule_v2", pulp.LpMinimize)

    x = pulp.LpVariable.dicts("x", (range(n_drones), range(n_stations), range(T)), cat="Binary")
    S = pulp.LpVariable.dicts("S", (range(n_drones), range(T + 1)), lowBound=sigma, upBound=1.0)
    z = pulp.LpVariable.dicts("z", (range(n_drones), range(T), range(n_bands)), cat="Binary")

    u = {}
    valid_t_for_k = {}
    for k, m in enumerate(missions):
        lo_t, hi_t = m["release_slot"], T - m["duration_slots"]
        valid_t_for_k[k] = list(range(lo_t, hi_t + 1)) if hi_t >= lo_t else []
        if not valid_t_for_k[k]:
            raise ValueError(f"mission {k} has no feasible start slot within the horizon (T={T})")
        for i in range(n_drones):
            for t in valid_t_for_k[k]:
                u[(i, k, t)] = pulp.LpVariable(f"u_{i}_{k}_{t}", cat="Binary")

    C = [pulp.LpVariable(f"C_{k}", lowBound=0) for k in range(K)]
    Tk = [pulp.LpVariable(f"T_{k}", lowBound=0) for k in range(K)]
    Cmax = pulp.LpVariable("Cmax", lowBound=0)

    for k in range(K):  # C5: every mission started exactly once
        prob += pulp.lpSum(u[(i, k, t)] for i in range(n_drones) for t in valid_t_for_k[k]) == 1

    def flying_expr(i, t):
        terms = [u[(i, k, t2)] for k, m in enumerate(missions)
                 for t2 in valid_t_for_k[k] if t2 <= t <= t2 + m["duration_slots"] - 1
                 and (i, k, t2) in u]
        return pulp.lpSum(terms) if terms else 0

    for i in range(n_drones):
        prob += S[i][0] == S0[i]
        for t in range(T):
            x_total_t = pulp.lpSum(x[i][j][t] for j in range(n_stations))
            prob += x_total_t <= 1  # C2
            prob += flying_expr(i, t) + x_total_t <= 1  # A5 exclusivity

            mission_energy_t = pulp.lpSum((missions[k]["energy_wh"] / battery[i]) * u[(i, k, t)]
                                            for k in range(K) if (i, k, t) in u)

            prob += pulp.lpSum(z[i][t][l] for l in range(n_bands)) == 1
            for l, (lo, hi, rate) in enumerate(bands):
                prob += S[i][t] >= lo - BIG_M * (1 - z[i][t][l])
                prob += S[i][t] <= hi + BIG_M * (1 - z[i][t][l])
                for a_coef, b_coef in f13_pieces_for_band(l, dt_min, battery[i], eta):
                    prob += (S[i][t + 1] <= a_coef * S[i][t] + b_coef
                             + BIG_M * (2 - x_total_t - z[i][t][l]) - mission_energy_t)
            prob += S[i][t + 1] <= S[i][t] + BIG_M * x_total_t - mission_energy_t  # not-charging catch-all
            prob += S[i][t + 1] >= S[i][t] - mission_energy_t  # no free/artificial SoC drop

            if min_dwell_slots > 1:  # C10 (E9-fixed dwell truncation)
                x_prev = pulp.lpSum(x[i][j][t - 1] for j in range(n_stations)) if t > 0 else 0
                rising_edge = x_total_t - x_prev
                for t_prime in range(t, min(T, t + min_dwell_slots)):
                    x_total_tp = pulp.lpSum(x[i][j][t_prime] for j in range(n_stations))
                    prob += rising_edge <= x_total_tp

    for j in range(n_stations):
        for t in range(T):
            prob += pulp.lpSum(x[i][j][t] for i in range(n_drones)) <= pads[j]  # C1

    for k, m in enumerate(missions):  # C6
        D = m["duration_slots"]
        prob += C[k] == pulp.lpSum((t + D) * dt_min * u[(i, k, t)]
                                     for i in range(n_drones) for t in valid_t_for_k[k])
        prob += Tk[k] >= C[k] - m["deadline_min"]
        prob += Cmax >= C[k]  # C7

    energy_cost = pulp.lpSum(
        tariff_flat * (S[i][t + 1] - S[i][t] +
                        pulp.lpSum((missions[k]["energy_wh"] / battery[i]) * u[(i, k, t)]
                                    for k in range(K) if (i, k, t) in u)) * battery[i]
        for i in range(n_drones) for t in range(T))
    total_tardiness = pulp.lpSum(Tk)
    prob += alpha * Cmax + beta * energy_cost + gamma * total_tardiness

    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_sec)
    prob.solve(solver)
    status = pulp.LpStatus[prob.status]
    # Solver time-limit rule (addition 3, 2026-09-23): "Optimal" is the only
    # status where CBC has PROVEN optimality; anything else (e.g. a
    # feasible incumbent at a time-limit stop) must never be treated as
    # optimal for a gap computation -- callers must check is_optimal.
    is_optimal = (status == "Optimal")

    x_sol = {(i, j, t): int(round(pulp.value(x[i][j][t])))
             for i in range(n_drones) for j in range(n_stations) for t in range(T)}
    S_sol = {(i, t): pulp.value(S[i][t]) for i in range(n_drones) for t in range(T + 1)}
    u_sol = {key: int(round(pulp.value(var))) for key, var in u.items()}
    Z = pulp.value(prob.objective)
    Cmax_val = pulp.value(Cmax)

    # Hard capacity invariant on the SOLUTION itself (addition 4, 2026-09-23):
    # verify C1 directly from x_sol, independent of the solver's reported
    # status -- never trust "Optimal"/"Feasible" alone as proof C1 holds.
    for j in range(n_stations):
        for t in range(T):
            occ = sum(x_sol[(i, j, t)] for i in range(n_drones))
            if occ > pads[j]:
                raise AssertionError(
                    f"MILP v2 solution violates C1: station {j}, slot {t}, {occ} drones "
                    f"charging but only {pads[j]} pads")

    return {
        "status": status, "is_optimal": is_optimal, "objective": Z,
        "alpha_cmax_term": alpha * Cmax_val if Cmax_val is not None else None,
        "beta_energy_term": pulp.value(energy_cost), "gamma_tardy_term": pulp.value(total_tardiness),
        "x": x_sol, "u": u_sol, "S": S_sol,
        "C": [pulp.value(c) for c in C], "Tk": [pulp.value(tk) for tk in Tk],
        "Cmax": Cmax_val, "T": T, "n_drones": n_drones, "n_stations": n_stations,
    }


def solve_charge_schedule_ours_v2(n_drones: int, pads: list, S0: list, missions: list,
                                   battery_wh=90.0, sigma: float = 0.20,
                                   horizon_min: float = 360.0, dt_min: float = 10.0,
                                   alpha: float = 1.0, beta: float = 1.0, gamma: float = 1.0,
                                   tariff_flat: float = 0.15, w1: float = 1.0, w2: float = 1.0,
                                   recharge_trigger: float = 0.35,
                                   oracle_assignment: bool = False) -> dict:
    """Discretised 'ours' heuristic for MILP v2's SAME depot-abstracted
    instance, for a genuine apples-to-apples optimality gap (addition 2,
    2026-09-23): reuses sim/formulas.py's F5-F11 functions DIRECTLY (the
    identical functions sim/mission_sim.py's policy='ours' branch calls),
    not a second, independently-written implementation that could drift.
    Depot simplification collapses geometry to nothing -- every station is
    at distance 0 (tau_ij=0, e_ij=0), so F5's gate reduces to soc>=sigma,
    F8's cost reduces to W_j + T_chg (deterministic_wait + charge time),
    and F10's flight_time term is 0 (a mission's own duration is D_k, not
    a travel leg on top of it). Uses REMEDIATION.md Section 2's raw F12
    (same units as solve_charge_schedule_milp_v2's objective), not
    mission_sim.py's normalized reporting variant.

    oracle_assignment (2026-09-23, X7 gap follow-up): in the X7 instance
    generator every mission has release_slot=0, so the heuristic ALREADY
    has full information about every mission from t=0 -- there is no
    literal rolling-horizon information gap to close here. What IS
    different from the MILP is that mission-to-drone pairing is decided
    GREEDILY, one mission at a time (earliest deadline first, first idle
    drone that can afford it), never reconsidered. This flag replaces that
    with a ONE-SHOT globally-optimal bipartite assignment (Hungarian
    algorithm, scipy.optimize.linear_sum_assignment), computed once at
    t=0 from the same full mission list the greedy version already sees,
    minimizing each pairing's charging-energy shortfall
    (max(0, mission_energy/battery - (S0[i]-sigma))) summed over all
    pairs. Isolates "greedy pairing order" from "genuine future-information
    advantage" -- with both variants already seeing every mission
    up front, only the ASSIGNMENT RULE differs.
    """
    from sim.energy import time_to_reach_target_min
    from sim.formulas import charging_slack, combined_priority, deterministic_wait, margin, target_soc

    n_stations = len(pads)
    T = int(round(horizon_min / dt_min))
    battery = [battery_wh] * n_drones if isinstance(battery_wh, (int, float)) else battery_wh
    T_REF = time_to_reach_target_min(0.0, 1.0, battery[0])

    oracle_pairs = None  # k -> i, fixed drone for mission k, computed once
    if oracle_assignment:
        from scipy.optimize import linear_sum_assignment
        K = len(missions)
        n_pad = max(K, n_drones)
        cost = np.full((n_pad, n_pad), 1e6)
        for i in range(n_drones):
            for k, m in enumerate(missions):
                shortfall = max(0.0, m["energy_wh"] / battery[i] - (S0[i] - sigma))
                cost[i][k] = shortfall
        row_ind, col_ind = linear_sum_assignment(cost)
        oracle_pairs = {k: i for i, k in zip(row_ind, col_ind) if k < K and i < n_drones}

    S = [S0[i] for i in range(n_drones)]
    busy_until = [0] * n_drones  # slot index the drone is occupied through (mission or charge)
    charging = [False] * n_drones
    free_time_by_pad = [[0.0] * pads[j] for j in range(n_stations)]  # in SLOTS
    mission_start = {}  # k -> (i, t)
    mission_done = [False] * len(missions)
    x_sol = {(i, j, t): 0 for i in range(n_drones) for j in range(n_stations) for t in range(T)}
    completion_slot = [None] * len(missions)
    charging_energy_wh_total = 0.0

    for t in range(T):
        for i in range(n_drones):  # 1. charging that finishes exactly at t becomes idle
            if charging[i] and busy_until[i] == t:
                charging[i] = False

        # Only charge if there's still unfinished work in this CLOSED,
        # finite-mission instance -- unlike mission_sim.py's open-ended
        # engine (always topping off an idle drone for a next mission that
        # may arrive later), a MILP-comparison instance has a fixed mission
        # list, so charging after every mission is done just wastes energy
        # cost for no benefit. Bug found via the hand-checkable instance:
        # without this guard, a drone that just finished its only mission
        # kept re-triggering charge-to-full (s_req falls back to 1.0-sigma
        # with no next mission) for several extra slots it would never use.
        any_work_remaining = any(not mission_done[k] for k in range(len(missions)))
        needing = [i for i in range(n_drones) if busy_until[i] <= t and not charging[i]
                   and S[i] <= recharge_trigger + 1e-9
                   and (any_work_remaining or S[i] < sigma - 1e-9)]
        ranked = []
        for i in needing:
            nm_k = next((k for k, m in enumerate(missions) if not mission_done[k]
                         and m["release_slot"] <= t), None)
            slack = (charging_slack(missions[nm_k]["deadline_min"], t * dt_min, 0.0, horizon_min)
                     if nm_k is not None else horizon_min)
            marg = margin((0, 0), [], S[i], battery[i])  # depot: no travel energy to any station
            prio = combined_priority(slack, marg, w1, w2, T_REF)
            ranked.append((prio, i, nm_k))
        ranked.sort(key=lambda r: -r[0])

        for prio, i, nm_k in ranked:
            s_req = (missions[nm_k]["energy_wh"] / battery[i]) if nm_k is not None else (1.0 - sigma)
            s_tgt = target_soc(s_req, recharge_trigger)
            best_J, best_j, best_pad, best_start = None, None, None, None
            for j in range(n_stations):
                T_chg_slots = time_to_reach_target_min(S[i], s_tgt, battery[i]) / dt_min
                W_j, start, pad = deterministic_wait(free_time_by_pad[j], t)
                J = W_j + T_chg_slots
                if best_J is None or J < best_J:
                    best_J, best_j, best_pad, best_start = J, j, pad, start
            T_chg_slots = math.ceil(time_to_reach_target_min(S[i], s_tgt, battery[i]) / dt_min - 1e-9)
            if T_chg_slots <= 0:
                continue
            start_slot = max(t, int(round(best_start)))
            end_slot = start_slot + T_chg_slots
            free_time_by_pad[best_j][best_pad] = end_slot
            for tt in range(start_slot, end_slot):
                x_sol[(i, best_j, tt)] = 1
            charging_energy_wh_total += (s_tgt - S[i]) * battery[i]
            busy_until[i] = end_slot
            charging[i] = True
            S[i] = s_tgt

        idle = [i for i in range(n_drones) if busy_until[i] <= t and not charging[i]]
        avail_missions = [k for k, m in enumerate(missions)
                           if not mission_done[k] and m["release_slot"] <= t and k not in mission_start]
        avail_missions.sort(key=lambda k: missions[k]["deadline_min"])
        for k in avail_missions:
            if oracle_pairs is not None:
                # Fixed pairing (Hungarian algorithm, computed once at t=0):
                # only the pre-assigned drone may take this mission -- wait
                # for it rather than opportunistically grabbing whichever
                # drone happens to be idle first.
                i = oracle_pairs.get(k)
                if i is None or i not in idle:
                    continue
                need = missions[k]["energy_wh"] / battery[i]
                if S[i] - need >= sigma - 1e-9:
                    mission_start[k] = (i, t)
                    D = missions[k]["duration_slots"]
                    busy_until[i] = t + D
                    S[i] -= need
                    completion_slot[k] = t + D
                    mission_done[k] = True
                    idle.remove(i)
                continue
            for i in list(idle):
                need = missions[k]["energy_wh"] / battery[i]
                if S[i] - need >= sigma - 1e-9:
                    mission_start[k] = (i, t)
                    D = missions[k]["duration_slots"]
                    busy_until[i] = t + D
                    S[i] -= need
                    completion_slot[k] = t + D
                    mission_done[k] = True
                    idle.remove(i)
                    break

    unfinished = [k for k in range(len(missions)) if not mission_done[k]]

    # Capacity invariant (addition 4), same check as the MILP's own.
    occupancy = {}
    for (i, j, tt), v in x_sol.items():
        if v == 1:
            occupancy[(j, tt)] = occupancy.get((j, tt), 0) + 1
    for (j, tt), occ in occupancy.items():
        if occ > pads[j]:
            raise AssertionError(f"ours_v2 heuristic solution violates C1: station {j}, slot {tt}, "
                                  f"{occ} drones charging but only {pads[j]} pads")

    C_k = [completion_slot[k] * dt_min if completion_slot[k] is not None else None
           for k in range(len(missions))]
    Tk = [max(0.0, ck - missions[k]["deadline_min"]) if ck is not None else None
          for k, ck in enumerate(C_k)]
    Cmax = max((ck for ck in C_k if ck is not None), default=0.0)
    total_tardiness = sum(tk for tk in Tk if tk is not None)
    energy_cost = tariff_flat * charging_energy_wh_total
    Z = alpha * Cmax + beta * energy_cost + gamma * total_tardiness

    return {
        "status": "Infeasible" if unfinished else "Heuristic",
        "unfinished_missions": unfinished,
        "objective": Z if not unfinished else None,
        "alpha_cmax_term": alpha * Cmax, "beta_energy_term": energy_cost,
        "gamma_tardy_term": gamma * total_tardiness,
        "Cmax": Cmax, "total_tardiness": total_tardiness, "C": C_k, "Tk": Tk,
        "x": x_sol, "T": T, "n_drones": n_drones, "n_stations": n_stations,
    }
