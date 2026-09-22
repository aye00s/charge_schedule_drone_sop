"""REMEDIATION.md Section 2's F1-F14: pure, testable formula functions for
the project's actual proposed method ("ours" policy, integrated into
sim/mission_sim.py::run_mission_sim as policy='ours', 2026-09-22 checkpoint
4 rework -- previously a separate sim/ours_policy.py module, since deleted).
F5 (dispatch gate + mission slack) and F2/F3/F4 already live in
sim/mission_sim.py and sim/energy.py -- reused, not duplicated, here.

2-leg modelling decision (CLAUDE.md Section 13, 2026-09-22): missions have
a single destination, no separate origin distinct from a drone's current
position. F5/F6/F10 below are already in that 2-leg form.
"""

import math

from sim.energy import flight_energy_wh, time_to_reach_target_min
from sim.tariff import FLAT_RATE_USD_PER_WH

SIGMA = 0.20


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def station_gate(position, station_positions, soc, battery_wh, sigma: float = SIGMA):
    """F5, station gate: F_i(t) = {j : S_i(t) - e_ij/B >= sigma}. A hard
    feasibility filter, evaluated before any cost is scored -- returns the
    list of station INDICES that pass."""
    F_i = []
    for j, sp in enumerate(station_positions):
        e = flight_energy_wh(distance(position, sp))
        if soc - e / battery_wh >= sigma - 1e-9:
            F_i.append(j)
    return F_i


def margin(position, station_positions, soc, battery_wh, sigma: float = SIGMA):
    """F11's margin_i = S_i(t) - sigma - min_j e_ij/B -- how much SoC
    headroom remains above the reserve once the CHEAPEST reachable-station
    leg is subtracted. margin_i < 0 means no station is reachable with
    reserve intact (should be 0 occurrences with a correct dispatch gate)."""
    if not station_positions:
        return soc - sigma
    min_e = min(flight_energy_wh(distance(position, sp)) for sp in station_positions)
    return soc - sigma - min_e / battery_wh


def target_soc(s_req: float, recharge_trigger: float, sigma: float = SIGMA,
               floor_margin: float = 0.05) -> float:
    """F6: S_tgt = min(1, max(S_req + sigma, S_trigger + floor_margin)).
    The floor prevents the zero-duration charge loop found in Phase 4
    (target landing below the UAV's own recharge trigger re-triggers
    charging immediately). If no mission is expected, pass s_req=0 so the
    max collapses to the floor -- callers that want "top off fully when
    nothing is expected" should pass s_req=1.0-sigma instead (see
    run_mission_sim's policy='ours' branch in sim/mission_sim.py)."""
    floor = recharge_trigger + floor_margin
    return min(1.0, max(s_req + sigma, floor))


def deterministic_wait(free_time_by_pad: list, t_arr: float):
    """F7: for a drone arriving at station j at t_arr, with each pad p's
    free_time[p] known (deterministic once travel times and charge
    durations are deterministic, which they are here), the pad start time
    is max(t_arr, min_p free_time[p]) and W_j(t_arr) is the gap. Returns
    (W_j, start_time, best_pad_index)."""
    best_pad = min(range(len(free_time_by_pad)), key=lambda p: free_time_by_pad[p])
    start = max(t_arr, free_time_by_pad[best_pad])
    return start - t_arr, start, best_pad


def time_to_ready_cost(tau_ij: float, free_time_by_pad: list, t: float, s_arr: float,
                        s_tgt: float, battery_wh: float, use_queue_term: bool = True,
                        use_charge_time_term: bool = True):
    """F8: J_ij(t) = tau_ij + W_j(t+tau_ij) + T_chg(S_arr, S_tgt). All three
    terms are in minutes. The queue term is evaluated at the ARRIVAL time
    t+tau_ij, not now -- REMEDIATION.md is explicit about this. Ablation
    flags drop the queue term (-> nearest-time greedy, baseline B3) or the
    charge-time term. Returns (J_ij, W_j, start_time, best_pad_index)."""
    t_arr = t + tau_ij
    if use_queue_term:
        W_j, start, best_pad = deterministic_wait(free_time_by_pad, t_arr)
    else:
        W_j, start, best_pad = 0.0, t_arr, min(range(len(free_time_by_pad)),
                                                key=lambda p: free_time_by_pad[p])
    T_chg = time_to_reach_target_min(s_arr, s_tgt, battery_wh) if use_charge_time_term else 0.0
    return tau_ij + W_j + T_chg, W_j, start, best_pad


def charging_slack(next_mission_deadline, t: float, flight_time_min: float, slack_cap: float):
    """F10, charging slack: slack_i = d_i - (t + flight_time_i), where d_i
    is the deadline of the drone's next (expected) mission and
    flight_time_i is the 2-leg flight time (current position directly to
    that mission's destination). If no mission is expected, slack_i =
    SLACK_CAP (a large constant, e.g. the horizon length)."""
    if next_mission_deadline is None:
        return slack_cap
    return next_mission_deadline - (t + flight_time_min)


def combined_priority(slack: float, margin_val: float, w1: float, w2: float,
                       t_ref: float, sigma: float = SIGMA, eps_t: float = 1.0,
                       eps_s: float = 0.01) -> float:
    """F11: normalised combined priority (slack in minutes, margin as a
    fraction -- the raw w1/slack + w2/margin form would carry mismatched
    units). If slack<=0 or margin<=0, priority is +inf (handle first --
    a feasibility emergency pre-empts the normal ranking)."""
    if slack <= 0 or margin_val <= 0:
        return math.inf
    return w1 * t_ref / max(slack, eps_t) + w2 * sigma / max(margin_val, eps_s)


def jit_departure_time(t: float, reservation_start: float, tau_ij_star: float) -> float:
    """F14: depart just late enough to arrive exactly when the reserved pad
    frees, instead of departing now and queueing on the pad physically.
    t_dep = max(t, start - tau_ij*)."""
    return max(t, reservation_start - tau_ij_star)


def objective_F12(makespan_min: float, horizon_min: float, total_cost_usd: float,
                   total_mission_flight_energy_wh: float, total_tardiness_min: float,
                   n_missions: int, mean_mission_duration_min: float,
                   alpha: float = 1.0, beta: float = 1.0, gamma: float = 1.0):
    """F12: min Z = alpha*C_max + beta*sum(pi*r*dt/60*x) + gamma*sum(T_k),
    reported with each of the three terms NORMALIZED (CLAUDE.md Section 13's
    Section 7 answer, 2026-09-22):
      - C_max term:   makespan / horizon_min
      - energy term:  total_cost_usd / (FLAT_RATE_USD_PER_WH * total_mission_flight_energy_wh)
                       -- always normalized against the FLAT tariff price,
                       even when the run itself used time-of-use pricing, so
                       ToU runs are judged on a common scale.
      - tardiness term: total_tardiness_min / (n_missions * mean_mission_duration_min)

    total_mission_flight_energy_wh must be MISSION-flight energy only
    (excludes charger-trip legs) -- a rule added 2026-09-22 after the user
    pointed out that energy spent flying to/from a charger is not "mission"
    energy and would understate the energy term's true cost-per-useful-work
    if included in the denominator.

    mean_mission_duration_min: this project's deadline_window_min is used
    here (a fixed, run-independent constant, the same for every mission in
    this model) rather than the empirical mean completion time, which
    would let a policy that makes missions take LONGER shrink its own
    tardiness term -- an assumption, not a value given verbatim in
    REMEDIATION.md's F12 spec, documented here and in CLAUDE.md.

    Returns (Z, c_max_term, energy_term, tardiness_term). Any zero
    denominator yields a 0.0 term (not an error) rather than blowing up on
    a degenerate/empty run."""
    c_max_term = makespan_min / horizon_min if horizon_min > 0 else 0.0
    energy_denom = FLAT_RATE_USD_PER_WH * total_mission_flight_energy_wh
    energy_term = total_cost_usd / energy_denom if energy_denom > 0 else 0.0
    tardy_denom = n_missions * mean_mission_duration_min
    tardy_term = total_tardiness_min / tardy_denom if tardy_denom > 0 else 0.0
    Z = alpha * c_max_term + beta * energy_term + gamma * tardy_term
    return Z, c_max_term, energy_term, tardy_term
