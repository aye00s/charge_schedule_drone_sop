"""Phase 4 mission-layer engine: real UAVs flying real missions, draining
batteries via the flight energy model, generating charge requests as an
EMERGENT consequence rather than an exogenous Poisson process (4.1).
Tracks deadlines/tardiness (4.2), uses the CC-CV charging curve so service
time depends on arrival SoC -- an M/G/c system, the paper's formulas no
longer apply (4.3) -- and supports full vs. adaptive-partial charge targets
(4.4).

Discrete time stepping, dt_min = 1 minute (assumption A1/A4). Safe SoC
reserve sigma = 0.20 (C3); reachability gate before any departure (C8-like,
simplified: enough energy to arrive with sigma remaining, no CC-CV lookahead
needed since only flight energy is spent en route).

policy (2026-09-22, REMEDIATION.md checkpoint 4 -- this replaces the
earlier, separate sim/ours_policy.py, which duplicated this file's flight/
mission bookkeeping instead of being integrated as REMEDIATION.md Section 3
literally specifies: "Implement as a policy policy='ours' in the Phase 4
mission simulator"):
  'baseline' (default) -- the original dispatch: threshold-triggered
      (S<=S_trigger), nearest-station routing, no queue-awareness, no
      reservation. Governed by charge_policy ('full'/'adaptive') and
      pad_order ('fcfs'/'margin'). Per REMEDIATION.md Section 6, this ONE
      configuration realises BOTH named baselines B1 (Threshold: charge to
      100% when S<=S_trigger, nearest station -- exactly charge_policy=
      'full') and B2 (FCFS: first requester gets first free pad, nearest
      station -- exactly pad_order='fcfs', the default). The model has no
      axis that would separate "threshold-triggered full charge" from
      "FCFS pad admission" -- both are simultaneously true of the one
      existing dispatch mechanism, so B1 and B2 are not distinguishable
      configurations here, not two different code paths.
  'jsq' -- B4: route to the reachable station with fewest drones in
      system (pads_busy + queue length), no reservation/free-time
      projection (ties broken on a separate RNG stream, same pattern as
      sim/scheduler.py's E3 fix). Always full charge target, FCFS pad
      service (the paper's baseline doesn't specify anything else).
  'ours' -- the full heuristic (REMEDIATION.md Section 3): F1-F11, F14,
      with all six ablation flags. B3 (nearest-time greedy) is this policy
      with use_queue_term=False, not a separate code path.
"""

import math
import time

import numpy as np

from sim.energy import flight_energy_wh, soc_after_charging, time_to_reach_target_min
from sim.formulas import (charging_slack, combined_priority, distance as _f_distance,
                           jit_departure_time, margin, objective_F12, station_gate,
                           target_soc, time_to_ready_cost)
from sim.models import Mission, Station, UAV
from sim.tariff import TARIFFS

SIGMA = 0.20
RECHARGE_TRIGGER_SOC = 0.35
AREA_SIDE_M = 2000.0
SPEED_MPS = 15.0
BATTERY_WH = 90.0
DT_MIN = 1.0
LOOKAHEAD_MIN = 30.0  # how far ahead adaptive charging / 'ours' look for the next mission
T_REF_DEFAULT = time_to_reach_target_min(0.0, 1.0, BATTERY_WH)  # F11's T_ref, ~39min at defaults


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _mission_slack(mission, t, candidate_uavs):
    """F10 mission slack: deadline minus (now + flight time), using the
    nearest still-available drone as the flight-time proxy (exact
    assignment isn't known yet at ranking time). REMEDIATION.md E7: the
    previous sort key was raw deadline-t, which ignores flight duration
    entirely -- a mission with a later deadline but a much longer flight
    can have LESS slack than one with an earlier deadline and a short
    flight, and must be ranked more urgent."""
    if not candidate_uavs:
        return mission.deadline - t
    nearest_dist = min(_distance(u.position, mission.destination) for u in candidate_uavs)
    flight_time_min = nearest_dist / SPEED_MPS / 60.0
    return mission.deadline - (t + flight_time_min)


def _reachable(position, dest, soc, battery_wh):
    d = _distance(position, dest)
    soc_needed = flight_energy_wh(d) / battery_wh
    return (soc - soc_needed) >= SIGMA - 1e-9, soc_needed


def _reachable_with_return(position, dest, soc, battery_wh, station_positions):
    """Mission reachability must also leave the UAV able to reach SOME
    station from the mission destination afterward -- otherwise a mission
    can legally strand a drone at exactly sigma with nowhere left to go.
    Checking arrival-at-destination alone (the literal reading of C8) isn't
    enough; this was caught by a smoke test showing >1000 safety
    violations, nearly all repeated every tick from a handful of drones
    stuck with no reachable station once dropped off mid-map."""
    d_to_dest = _distance(position, dest)
    soc_to_dest = flight_energy_wh(d_to_dest) / battery_wh
    soc_after_arrival = soc - soc_to_dest
    if soc_after_arrival < SIGMA - 1e-9:
        return False, soc_to_dest
    best_return = min(flight_energy_wh(_distance(dest, st)) / battery_wh for st in station_positions)
    return (soc_after_arrival - best_return) >= SIGMA - 1e-9, soc_to_dest


def _move_toward(position, dest, max_dist):
    d = _distance(position, dest)
    if d <= max_dist:
        return dest, True, d
    frac = max_dist / d
    new_pos = (position[0] + (dest[0] - position[0]) * frac,
               position[1] + (dest[1] - position[1]) * frac)
    return new_pos, False, max_dist


def _ceil_to_tick(x: float, dt_min: float = DT_MIN) -> float:
    """Round a continuous duration UP to the next whole tick. F7/F8/F9 are
    specified in REMEDIATION.md as continuous-time formulas, but this
    engine can only ever register a state change at a tick boundary
    (t + DT_MIN, never at a fractional t) -- so a raw continuous travel
    time or charge duration silently understates how long the engine will
    actually take, and every reservation built on top of it (F9's
    free_time chain) drifts by a fraction of a tick. Found 2026-09-22:
    the deterministic-prediction test's 1-tick tolerance was masking a
    real, non-random +1-tick pileup (31% of 812 sessions, all cases where
    tau_ij or the free_time entry was already an exact tick multiple --
    e.g. a drone re-dispatched to the SAME station it just finished
    charging at, tau_ij=0 exactly) on top of a continuous 0-1 tick
    rounding smear for every other session. Quantizing tau_ij and T_chg to
    the tick grid before they feed F7/F9 makes every prediction land
    exactly where the engine will actually put it."""
    return math.ceil(x / dt_min - 1e-9) * dt_min


def _next_expected_mission(uav, missions, t, lookahead):
    """The most demanding unassigned mission releasing within `lookahead`
    of now that this UAV could plausibly take (same lookahead concept as
    the existing adaptive-charging policy, reused for F6/F10's "next
    expected mission"). Returns the Mission object, or None."""
    horizon_t = t + lookahead
    best = None
    best_need = -1.0
    for m in missions:
        if m.assigned_uav is not None or m.completed_time is not None:
            continue
        if not (t <= m.release_time <= horizon_t):
            continue
        need = flight_energy_wh(_distance(uav.position, m.destination)) / uav.battery_wh
        if need > 1.0 - SIGMA:
            continue  # unreachable even at full charge
        if need > best_need:
            best_need = need
            best = m
    return best


def run_mission_sim(n_uavs: int, station_positions: list, pads_per_station: int,
                     horizon_min: float, seed: int, mission_rate_per_min: float,
                     deadline_window_min: float = 45.0,
                     policy: str = "baseline",
                     charge_policy: str = None,
                     order: str = "fcfs", pad_order: str = None,
                     tariff: str = "flat", battery_wh: float = BATTERY_WH,
                     w1: float = 1.0, w2: float = 1.0,
                     use_queue_term: bool = True, use_reservation: bool = True,
                     use_priority: bool = True, use_partial: bool = True,
                     use_jit: bool = False, use_charge_time_term: bool = True,
                     initial_soc: float = 1.0, initial_positions: list = None,
                     drain_cap_min: float = 0.0,
                     alpha: float = 1.0, beta: float = 1.0, gamma: float = 1.0) -> dict:
    """policy: 'baseline' (default, backward compatible), 'jsq' (B4), or
    'ours' (the full heuristic, Section 3) -- see the module docstring.

    charge_policy: 'full' (always charge to 100%) or 'adaptive' (charge to
    the SoC needed for the most demanding mission releasing within
    LOOKAHEAD_MIN, plus sigma margin; top off fully if none is on the
    horizon). Only meaningful for policy='baseline'; passing it explicitly
    with policy='jsq'/'ours' raises ValueError (jsq is always full-charge;
    'ours' uses use_partial instead).
    order: 'fcfs' (missions assigned by release order) or 'priority'
    (least-slack-first: available missions are assigned by ascending
    mission slack (F10) to the first reachable idle UAV). Applies to every
    policy (orthogonal to charging dispatch).
    pad_order: 'fcfs' (arrival order, default) or 'margin' (serve the
    waiting UAV with lowest battery margin first, REMEDIATION.md E5 --
    kept only as an explicit ablation). Only meaningful for policy=
    'baseline'; 'jsq' is always FCFS-at-the-pad, 'ours' uses reservation-
    order service (F7-F9) inherently -- passing pad_order explicitly with
    either raises ValueError.
    tariff: 'flat' or 'tou' (time-of-use, Section 4.4's pi_jt term) -- cost
    is accumulated per tick (not per whole session) since price varies with
    time of day within a single charging session.
    w1, w2, use_queue_term, use_reservation, use_priority, use_partial,
    use_jit, use_charge_time_term: F11 weights and the six Section 3
    ablation flags -- only meaningful for policy='ours'; passing any of
    them away from its default with policy!='ours' raises ValueError.
    initial_soc, initial_positions: override the default (soc=1.0, random
    positions) starting state -- for controlled tests; available to every
    policy.
    drain_cap_min: after horizon_min, if this is > 0 and any released
    mission is still incomplete, keep advancing ticks (no new missions
    release) for up to this many additional minutes so in-flight/in-queue
    work can finish, instead of cutting off exactly at the horizon. Default
    0.0 = no drain (exact pre-2026-09-22 behaviour, for every policy).
    Needed for F12's C_max/tardiness terms to mean something on a run that
    would otherwise end mid-mission. `unfinished_at_cap` in the return
    dict reports how many released missions were still incomplete when the
    loop stopped (0 if none, whether or not draining was used).
    alpha, beta, gamma: F12 objective weights (default 1.0 each, the
    Section 7 answer). F12's Z and its three normalized terms are always
    computed and returned, for every policy, per REMEDIATION.md Section 6.
    """
    assert policy in ("baseline", "jsq", "ours")

    ours_only = dict(w1=w1, w2=w2, use_queue_term=use_queue_term, use_reservation=use_reservation,
                      use_priority=use_priority, use_partial=use_partial, use_jit=use_jit,
                      use_charge_time_term=use_charge_time_term)
    ours_only_defaults = dict(w1=1.0, w2=1.0, use_queue_term=True, use_reservation=True,
                               use_priority=True, use_partial=True, use_jit=False,
                               use_charge_time_term=True)
    if policy != "ours":
        bad = [k for k, v in ours_only.items() if v != ours_only_defaults[k]]
        if bad:
            raise ValueError(f"{bad} only apply to policy='ours' (got policy={policy!r})")

    if policy == "baseline":
        charge_policy_r = charge_policy if charge_policy is not None else "full"
        pad_order_r = pad_order if pad_order is not None else "fcfs"
    else:
        if charge_policy is not None:
            raise ValueError(f"charge_policy only applies to policy='baseline' (got policy={policy!r})")
        if pad_order is not None:
            raise ValueError(f"pad_order only applies to policy='baseline' (got policy={policy!r})")
        charge_policy_r = None
        pad_order_r = None

    assert charge_policy_r in (None, "full", "adaptive")
    assert order in ("fcfs", "priority")
    assert pad_order_r in (None, "fcfs", "margin")
    assert tariff in TARIFFS
    rate_fn = TARIFFS[tariff]

    rng = np.random.default_rng(seed)
    if initial_positions is not None:
        positions = initial_positions
    else:
        positions = [tuple(rng.uniform(0, AREA_SIDE_M, size=2)) for _ in range(n_uavs)]
    uavs = [UAV(id=i, position=positions[i], battery_wh=battery_wh, soc=initial_soc)
            for i in range(n_uavs)]
    stations = [Station(id=j, position=tuple(pos), num_pads=pads_per_station)
                for j, pos in enumerate(station_positions)]

    # Pre-generate the mission stream (Poisson releases, random destinations)
    # -- identical draw sequence regardless of policy, so CRN holds across
    # policy comparisons at the same seed.
    missions = []
    t = 0.0
    mid = 0
    if mission_rate_per_min > 0:  # 0 means "no missions" -- controlled unit tests
        while True:
            t += rng.exponential(1.0 / mission_rate_per_min)
            if t > horizon_min:
                break
            dest = tuple(rng.uniform(0, AREA_SIDE_M, size=2))
            missions.append(Mission(id=mid, destination=dest, release_time=t,
                                     deadline=t + deadline_window_min))
            mid += 1
    missions.sort(key=lambda m: m.release_time)

    safety_violations = 0
    charge_sessions = []
    request_times = []
    total_cost_usd = 0.0
    mission_flight_energy_wh = 0.0
    gate_evaluations = 0  # F5 reachability-gate binding rate (Section 12's
    gate_refusals = 0     # pitfall: "if the gate never binds, log it"), same
                           # counters used by every policy for a uniform metric
    stampede_station_counts = []  # only populated by policy='ours'
    next_mission_idx = 0
    max_dist_per_tick = SPEED_MPS * DT_MIN * 60.0

    request_time_by_uav = {}  # uav.id -> dispatch tick, for total_delay_min (all 3 policies)
    on_pad_queue_ticks = 0.0  # time-integrated WAITING_FOR_PAD count, all 3 policies
    dispatch_wall_time_s = 0.0  # wall-clock spent in the dispatch-decision block only
                                  # (F7-F11 for 'ours'; the reachability+nearest/JSQ
                                  # selection loop for baseline/jsq) -- NOT movement,
                                  # charging, or mission assignment.
    final_t = 0.0  # actual elapsed simulated time when the loop stops (== the drain
                    # cap if drain was used and still exhausted, else <= it)

    # 'ours'-only state (harmless to initialise unconditionally)
    free_time = [[0.0] * pads_per_station for _ in stations]
    reservation = {}
    charge_start_soc = {}
    charge_start_time = {}
    # 'jsq'-only: separate tie-break stream (E3's pattern), never touches
    # the arrival/service/slack RNG draws above.
    jsq_tie_rng = np.random.default_rng(seed * 1_000_003 + 7919)

    fixed_steps = int(math.ceil(horizon_min / DT_MIN))
    step = 0
    while True:
        if step < fixed_steps:
            t = step * DT_MIN
        elif (drain_cap_min > 0 and any(m.completed_time is None for m in missions)
              and (step - fixed_steps) * DT_MIN < drain_cap_min):
            t = step * DT_MIN
        else:
            break

        while next_mission_idx < len(missions) and missions[next_mission_idx].release_time <= t:
            next_mission_idx += 1  # just reveals availability; assignment below scans all unassigned

        # ============================== BASELINE ==============================
        if policy == "baseline":
            _dispatch_t0 = time.perf_counter()
            needs_mission_uavs = []
            for uav in uavs:
                if uav.state != "IDLE":
                    continue

                if uav.soc <= RECHARGE_TRIGGER_SOC:
                    candidates = []
                    for st in stations:
                        gate_evaluations += 1
                        ok, _ = _reachable(uav.position, st.position, uav.soc, uav.battery_wh)
                        if ok:
                            candidates.append((_distance(uav.position, st.position), st))
                        else:
                            gate_refusals += 1
                    if candidates:
                        candidates.sort(key=lambda c: c[0])
                        _, st = candidates[0]
                        uav.state = "FLYING_TO_STATION"
                        uav.station_id = st.id
                        uav.dest = st.position
                        request_times.append(t)
                        request_time_by_uav[uav.id] = t
                    else:
                        safety_violations += 1
                    continue

                needs_mission_uavs.append(uav)
            dispatch_wall_time_s += time.perf_counter() - _dispatch_t0

            if order == "priority":
                available = [m for m in missions
                             if m.assigned_uav is None and m.release_time <= t and m.completed_time is None]
                available.sort(key=lambda m: _mission_slack(m, t, needs_mission_uavs))
                remaining_uavs = list(needs_mission_uavs)
                for m in available:
                    for uav in remaining_uavs:
                        ok, _ = _reachable_with_return(uav.position, m.destination, uav.soc,
                                                        uav.battery_wh, station_positions)
                        if ok:
                            m.assigned_uav = uav.id
                            uav.mission_id = m.id
                            uav.state = "FLYING_MISSION"
                            uav.dest = m.destination
                            remaining_uavs.remove(uav)
                            break
            else:
                for uav in needs_mission_uavs:
                    available = [m for m in missions
                                 if m.assigned_uav is None and m.release_time <= t and m.completed_time is None]
                    available.sort(key=lambda m: m.release_time)
                    for m in available:
                        ok, _ = _reachable_with_return(uav.position, m.destination, uav.soc,
                                                        uav.battery_wh, station_positions)
                        if ok:
                            m.assigned_uav = uav.id
                            uav.mission_id = m.id
                            uav.state = "FLYING_MISSION"
                            uav.dest = m.destination
                            break

            for uav in uavs:
                if uav.state not in ("FLYING_MISSION", "FLYING_TO_STATION"):
                    continue
                new_pos, arrived, dist_moved = _move_toward(uav.position, uav.dest, max_dist_per_tick)
                energy_wh = flight_energy_wh(dist_moved)
                uav.soc -= energy_wh / uav.battery_wh
                uav.position = new_pos
                if uav.state == "FLYING_MISSION":
                    mission_flight_energy_wh += energy_wh
                if uav.soc < SIGMA - 1e-6:
                    safety_violations += 1
                if arrived:
                    if uav.state == "FLYING_MISSION":
                        mission = next(m for m in missions if m.id == uav.mission_id)
                        mission.completed_time = t + DT_MIN
                        uav.state = "IDLE"
                        uav.mission_id = None
                        uav.dest = None
                    else:  # FLYING_TO_STATION
                        st = stations[uav.station_id]
                        if charge_policy_r == "adaptive":
                            target = _adaptive_target(uav, missions, t, DT_MIN)
                        else:
                            target = 1.0
                        uav.charge_target = target
                        uav.dest = None
                        if st.pads_busy < st.num_pads:
                            st.pads_busy += 1
                            uav.state = "CHARGING"
                            uav.charge_start_soc = uav.soc
                            uav.charge_start_time = t + DT_MIN
                        else:
                            uav.state = "WAITING_FOR_PAD"
                            st.queue.append(uav.id)

            for uav in uavs:
                if uav.state != "CHARGING":
                    continue
                soc_before_tick = uav.soc
                new_soc = soc_after_charging(uav.soc, DT_MIN, uav.battery_wh)
                new_soc = min(new_soc, uav.charge_target)
                uav.soc = new_soc
                energy_this_tick_wh = (new_soc - soc_before_tick) * uav.battery_wh
                total_cost_usd += energy_this_tick_wh * rate_fn(t)
                if uav.soc >= uav.charge_target - 1e-6:
                    st = stations[uav.station_id]
                    req_t = request_time_by_uav.get(uav.id)
                    charge_sessions.append({
                        "uav": uav.id, "station": st.id, "start_soc": uav.charge_start_soc,
                        "target_soc": uav.charge_target,
                        "duration_min": (t + DT_MIN) - uav.charge_start_time,
                        "energy_wh": (uav.soc - uav.charge_start_soc) * uav.battery_wh,
                        "request_time": req_t,
                        "total_delay_min": (uav.charge_start_time - req_t) if req_t is not None else None,
                    })
                    st.pads_busy -= 1
                    uav.state = "IDLE"
                    uav.station_id = None
                    if st.queue:
                        if pad_order_r == "margin":
                            uav_by_id = {u.id: u for u in uavs}
                            best_pos = min(range(len(st.queue)),
                                           key=lambda k: uav_by_id[st.queue[k]].soc)
                            next_uav_id = st.queue.pop(best_pos)
                        else:
                            next_uav_id = st.queue.pop(0)
                        next_uav = next(u for u in uavs if u.id == next_uav_id)
                        st.pads_busy += 1
                        next_uav.state = "CHARGING"
                        next_uav.charge_start_soc = next_uav.soc
                        next_uav.charge_start_time = t + DT_MIN

        # ================================ JSQ (B4) =============================
        elif policy == "jsq":
            _dispatch_t0 = time.perf_counter()
            needs_mission_uavs = []
            for uav in uavs:
                if uav.state != "IDLE":
                    continue

                if uav.soc <= RECHARGE_TRIGGER_SOC:
                    candidates = []
                    for st in stations:
                        gate_evaluations += 1
                        ok, _ = _reachable(uav.position, st.position, uav.soc, uav.battery_wh)
                        if ok:
                            in_system = st.pads_busy + len(st.queue)
                            candidates.append((in_system, st))
                        else:
                            gate_refusals += 1
                    if candidates:
                        best = min(c[0] for c in candidates)
                        tied = [c[1] for c in candidates if c[0] == best]
                        st = tied[0] if len(tied) == 1 else tied[int(jsq_tie_rng.integers(len(tied)))]
                        uav.state = "FLYING_TO_STATION"
                        uav.station_id = st.id
                        uav.dest = st.position
                        request_times.append(t)
                        request_time_by_uav[uav.id] = t
                    else:
                        safety_violations += 1
                    continue

                needs_mission_uavs.append(uav)
            dispatch_wall_time_s += time.perf_counter() - _dispatch_t0

            if order == "priority":
                available = [m for m in missions
                             if m.assigned_uav is None and m.release_time <= t and m.completed_time is None]
                available.sort(key=lambda m: _mission_slack(m, t, needs_mission_uavs))
                remaining_uavs = list(needs_mission_uavs)
                for m in available:
                    for uav in remaining_uavs:
                        ok, _ = _reachable_with_return(uav.position, m.destination, uav.soc,
                                                        uav.battery_wh, station_positions)
                        if ok:
                            m.assigned_uav = uav.id
                            uav.mission_id = m.id
                            uav.state = "FLYING_MISSION"
                            uav.dest = m.destination
                            remaining_uavs.remove(uav)
                            break
            else:
                for uav in needs_mission_uavs:
                    available = [m for m in missions
                                 if m.assigned_uav is None and m.release_time <= t and m.completed_time is None]
                    available.sort(key=lambda m: m.release_time)
                    for m in available:
                        ok, _ = _reachable_with_return(uav.position, m.destination, uav.soc,
                                                        uav.battery_wh, station_positions)
                        if ok:
                            m.assigned_uav = uav.id
                            uav.mission_id = m.id
                            uav.state = "FLYING_MISSION"
                            uav.dest = m.destination
                            break

            for uav in uavs:
                if uav.state not in ("FLYING_MISSION", "FLYING_TO_STATION"):
                    continue
                new_pos, arrived, dist_moved = _move_toward(uav.position, uav.dest, max_dist_per_tick)
                energy_wh = flight_energy_wh(dist_moved)
                uav.soc -= energy_wh / uav.battery_wh
                uav.position = new_pos
                if uav.state == "FLYING_MISSION":
                    mission_flight_energy_wh += energy_wh
                if uav.soc < SIGMA - 1e-6:
                    safety_violations += 1
                if arrived:
                    if uav.state == "FLYING_MISSION":
                        mission = next(m for m in missions if m.id == uav.mission_id)
                        mission.completed_time = t + DT_MIN
                        uav.state = "IDLE"
                        uav.mission_id = None
                        uav.dest = None
                    else:  # FLYING_TO_STATION, B4 is always full-charge
                        st = stations[uav.station_id]
                        uav.charge_target = 1.0
                        uav.dest = None
                        if st.pads_busy < st.num_pads:
                            st.pads_busy += 1
                            uav.state = "CHARGING"
                            uav.charge_start_soc = uav.soc
                            uav.charge_start_time = t + DT_MIN
                        else:
                            uav.state = "WAITING_FOR_PAD"
                            st.queue.append(uav.id)

            for uav in uavs:
                if uav.state != "CHARGING":
                    continue
                soc_before_tick = uav.soc
                new_soc = soc_after_charging(uav.soc, DT_MIN, uav.battery_wh)
                new_soc = min(new_soc, uav.charge_target)
                uav.soc = new_soc
                energy_this_tick_wh = (new_soc - soc_before_tick) * uav.battery_wh
                total_cost_usd += energy_this_tick_wh * rate_fn(t)
                if uav.soc >= uav.charge_target - 1e-6:
                    st = stations[uav.station_id]
                    req_t = request_time_by_uav.get(uav.id)
                    charge_sessions.append({
                        "uav": uav.id, "station": st.id, "start_soc": uav.charge_start_soc,
                        "target_soc": uav.charge_target,
                        "duration_min": (t + DT_MIN) - uav.charge_start_time,
                        "energy_wh": (uav.soc - uav.charge_start_soc) * uav.battery_wh,
                        "request_time": req_t,
                        "total_delay_min": (uav.charge_start_time - req_t) if req_t is not None else None,
                    })
                    st.pads_busy -= 1
                    uav.state = "IDLE"
                    uav.station_id = None
                    if st.queue:  # B4 is always FCFS at the pad
                        next_uav_id = st.queue.pop(0)
                        next_uav = next(u for u in uavs if u.id == next_uav_id)
                        st.pads_busy += 1
                        next_uav.state = "CHARGING"
                        next_uav.charge_start_soc = next_uav.soc
                        next_uav.charge_start_time = t + DT_MIN

        # ================================ OURS =================================
        else:
            _dispatch_t0 = time.perf_counter()
            # --- Step 1: which drones need a charging decision ---
            C = []
            for uav in uavs:
                if uav.state != "IDLE" or uav.id in reservation:
                    continue
                needs = uav.soc <= RECHARGE_TRIGGER_SOC
                if not needs:
                    nm = _next_expected_mission(uav, missions, t, LOOKAHEAD_MIN)
                    if nm is not None:
                        ok, _ = _reachable_with_return(uav.position, nm.destination, uav.soc,
                                                        uav.battery_wh, station_positions)
                        needs = not ok
                if needs:
                    C.append(uav)

            # --- Step 2: rank by F10 (charging slack) + F11 (combined priority) ---
            ranked = []
            for uav in C:
                nm = _next_expected_mission(uav, missions, t, LOOKAHEAD_MIN)
                if nm is not None:
                    flight_time = _distance(uav.position, nm.destination) / SPEED_MPS / 60.0
                    slack = charging_slack(nm.deadline, t, flight_time, slack_cap=horizon_min)
                else:
                    slack = horizon_min  # SLACK_CAP
                marg = margin(uav.position, station_positions, uav.soc, uav.battery_wh)
                prio = (combined_priority(slack, marg, w1, w2, T_REF_DEFAULT)
                        if use_priority else 0.0)  # False -> FIFO (request order), no ranking
                ranked.append((prio, uav, nm, marg))
            if use_priority:
                ranked.sort(key=lambda r: -r[0])  # descending priority = most urgent first

            # --- Step 3: assign stations with reservation (F5-F9, F14) ---
            this_epoch_stations = []
            for prio, uav, nm, marg in ranked:
                F_i = station_gate(uav.position, station_positions, uav.soc, uav.battery_wh)
                gate_evaluations += len(station_positions)
                gate_refusals += len(station_positions) - len(F_i)
                if not F_i:
                    safety_violations += 1
                    continue

                if use_partial:
                    if nm is not None:
                        # F6's S_req = (e_{j->d_k} + min_j' e_{d_k->j'}) / B
                        e_to_dest = flight_energy_wh(_distance(uav.position, nm.destination))
                        e_return = min(flight_energy_wh(_distance(nm.destination, sp))
                                        for sp in station_positions)
                        s_req = (e_to_dest + e_return) / uav.battery_wh
                    else:
                        s_req = 1.0 - SIGMA  # no mission expected -> top off fully
                    s_tgt = target_soc(s_req, RECHARGE_TRIGGER_SOC)
                else:
                    s_tgt = 1.0

                best_J, best_j, best_W, best_start, best_pad = None, None, None, None, None
                for j in F_i:
                    tau_ij_raw = _f_distance(uav.position, station_positions[j]) / SPEED_MPS / 60.0
                    # F7 fix (2026-09-22): quantize to the tick the engine will
                    # actually arrive on -- see _ceil_to_tick's docstring.
                    tau_ij = max(DT_MIN, _ceil_to_tick(tau_ij_raw))
                    s_arr = uav.soc - flight_energy_wh(
                        _f_distance(uav.position, station_positions[j])) / uav.battery_wh
                    pads_state = free_time[j] if use_reservation else [t] * len(free_time[j])
                    J, W, start, pad = time_to_ready_cost(tau_ij, pads_state, t, s_arr, s_tgt,
                                                           uav.battery_wh, use_queue_term,
                                                           use_charge_time_term)
                    if best_J is None or J < best_J:
                        best_J, best_j, best_W, best_start, best_pad = J, j, W, start, pad

                tau_star = max(DT_MIN, _ceil_to_tick(
                    _f_distance(uav.position, station_positions[best_j]) / SPEED_MPS / 60.0))
                T_chg_raw = time_to_reach_target_min(
                    uav.soc - flight_energy_wh(_f_distance(uav.position, station_positions[best_j]))
                    / uav.battery_wh, s_tgt, uav.battery_wh) if use_charge_time_term else 0.0
                # Same fix for F9's free_time chain: a chained reservation's
                # predicted start must also land on a tick boundary, or the
                # NEXT drone's F7 prediction inherits the same drift.
                T_chg = _ceil_to_tick(T_chg_raw) if T_chg_raw > 0 else 0.0
                end = best_start + T_chg
                if use_reservation:
                    free_time[best_j][best_pad] = end  # F9: update BEFORE the next drone this epoch
                dep_time = jit_departure_time(t, best_start, tau_star) if use_jit else t

                reservation[uav.id] = {"station": best_j, "pad": best_pad, "start": best_start,
                                        "end": end, "dep_time": dep_time, "s_tgt": s_tgt,
                                        "tau": tau_star, "created_at": t}
                this_epoch_stations.append(best_j)
            if len(this_epoch_stations) > 1:
                stampede_station_counts.append(this_epoch_stations)
            dispatch_wall_time_s += time.perf_counter() - _dispatch_t0

            # --- Step 4: mission assignment (F10 mission slack, F5 dispatch gate) ---
            needs_mission_uavs = [u for u in uavs if u.state == "IDLE" and u.id not in reservation]
            available = [m for m in missions
                         if m.assigned_uav is None and m.release_time <= t and m.completed_time is None]
            available.sort(key=lambda m: _mission_slack(m, t, needs_mission_uavs))
            remaining = list(needs_mission_uavs)
            for m in available:
                for uav in remaining:
                    ok, _ = _reachable_with_return(uav.position, m.destination, uav.soc,
                                                    uav.battery_wh, station_positions)
                    if ok:
                        m.assigned_uav = uav.id
                        uav.mission_id = m.id
                        uav.state = "FLYING_MISSION"
                        uav.dest = m.destination
                        remaining.remove(uav)
                        break

            # --- Step 5: departures for reserved drones whose dep_time has arrived ---
            for uav in uavs:
                if uav.id in reservation and uav.state == "IDLE" and t >= reservation[uav.id]["dep_time"]:
                    res = reservation[uav.id]
                    uav.state = "FLYING_TO_STATION"
                    uav.station_id = res["station"]
                    uav.dest = station_positions[res["station"]]
                    request_times.append(t)

            # --- Step 6: advance flight ---
            for uav in uavs:
                if uav.state not in ("FLYING_MISSION", "FLYING_TO_STATION"):
                    continue
                new_pos, arrived, dist_moved = _move_toward(uav.position, uav.dest, max_dist_per_tick)
                energy_wh = flight_energy_wh(dist_moved)
                uav.soc -= energy_wh / uav.battery_wh
                uav.position = new_pos
                if uav.state == "FLYING_MISSION":
                    mission_flight_energy_wh += energy_wh
                if uav.soc < SIGMA - 1e-6:
                    safety_violations += 1
                if arrived:
                    if uav.state == "FLYING_MISSION":
                        mission = next(m for m in missions if m.id == uav.mission_id)
                        mission.completed_time = t + DT_MIN
                        uav.state = "IDLE"
                        uav.mission_id = None
                        uav.dest = None
                    else:  # FLYING_TO_STATION, arrived at its reserved pad
                        res = reservation[uav.id]
                        uav.dest = None
                        uav.charge_target = res["s_tgt"]
                        if t + DT_MIN >= res["start"] - 1e-6:
                            uav.state = "CHARGING"
                            charge_start_soc[uav.id] = uav.soc
                            charge_start_time[uav.id] = t + DT_MIN
                        else:
                            uav.state = "WAITING_FOR_PAD"  # reserved but pad not free yet (no JIT)

            # --- Step 7: waiting-for-reserved-pad -> charging once start arrives ---
            for uav in uavs:
                if uav.state == "WAITING_FOR_PAD" and uav.id in reservation:
                    if t + DT_MIN >= reservation[uav.id]["start"] - 1e-6:
                        uav.state = "CHARGING"
                        charge_start_soc[uav.id] = uav.soc
                        charge_start_time[uav.id] = t + DT_MIN

            # --- Step 8: charging ---
            for uav in uavs:
                if uav.state != "CHARGING":
                    continue
                soc_before = uav.soc
                new_soc = soc_after_charging(uav.soc, DT_MIN, uav.battery_wh)
                new_soc = min(new_soc, uav.charge_target)
                uav.soc = new_soc
                total_cost_usd += (new_soc - soc_before) * uav.battery_wh * rate_fn(t)
                if uav.soc >= uav.charge_target - 1e-6:
                    created_at = reservation[uav.id]["created_at"]
                    predicted_start = reservation[uav.id]["start"]
                    charge_sessions.append({
                        "uav": uav.id, "station": reservation[uav.id]["station"],
                        "start_soc": charge_start_soc[uav.id],
                        "target_soc": uav.charge_target,
                        "duration_min": (t + DT_MIN) - charge_start_time[uav.id],
                        "energy_wh": (uav.soc - charge_start_soc[uav.id]) * uav.battery_wh,
                        "request_time": created_at,
                        "total_delay_min": charge_start_time[uav.id] - created_at,
                        "predicted_start": predicted_start,
                        "realised_start": charge_start_time[uav.id],
                        # item 5 (2026-09-22): logged explicitly, not just
                        # derivable, so X6 can consume X3's own session logs
                        # directly instead of every caller re-subtracting.
                        "prediction_error_min": charge_start_time[uav.id] - predicted_start,
                    })
                    uav.state = "IDLE"
                    uav.station_id = None
                    del reservation[uav.id]

        # On-pad queue length, time-integrated (Section 7/12's "queue length
        # must be time-weighted" principle) -- counted once per tick, after
        # this tick's transitions, uniformly for all 3 policies since all of
        # them use the same WAITING_FOR_PAD state.
        on_pad_queue_ticks += sum(1 for uav in uavs if uav.state == "WAITING_FOR_PAD") * DT_MIN
        final_t = t + DT_MIN
        step += 1

    unfinished_at_cap = sum(1 for m in missions if m.completed_time is None)
    completed = [m for m in missions if m.completed_time is not None]
    tardy = [m for m in completed if m.completed_time > m.deadline]
    total_tardiness = sum(m.completed_time - m.deadline for m in tardy)
    makespan = max((m.completed_time for m in completed), default=0.0)
    # ^ all four of the above are the ORIGINAL (pre-checkpoint-4) definitions,
    # over completed missions only -- kept exactly as-is (legacy fields,
    # `test_regression.py`'s exact-reproduction test depends on them).

    # F12 accounting (2026-09-22, per user instruction): a mission still
    # incomplete when the loop stops must count as C_k = cap (`final_t`,
    # the actual elapsed simulated time at that point), not be silently
    # dropped from C_max and sum(T_k) -- excluding it understates both,
    # worst of all exactly when a policy is struggling (many unfinished).
    capped_C_k = [(m.completed_time if m.completed_time is not None else final_t) for m in missions]
    f12_makespan = max(capped_C_k, default=0.0)
    f12_tardiness = sum(max(0.0, ck - m.deadline) for ck, m in zip(capped_C_k, missions))

    Z, cmax_term, energy_term, tardy_term = objective_F12(
        makespan_min=f12_makespan, horizon_min=horizon_min, total_cost_usd=total_cost_usd,
        total_mission_flight_energy_wh=mission_flight_energy_wh,
        total_tardiness_min=f12_tardiness, n_missions=len(missions),
        mean_mission_duration_min=deadline_window_min, alpha=alpha, beta=beta, gamma=gamma)

    result = {
        "policy": policy,
        "missions_total": len(missions),
        "missions_completed": len(completed),
        "unfinished_at_cap": unfinished_at_cap,
        "tardy_count": len(tardy),
        "total_tardiness_min": total_tardiness,
        "safety_violations": safety_violations,
        "makespan_min": makespan,
        "charge_sessions": len(charge_sessions),
        "total_charge_energy_wh": sum(cs["energy_wh"] for cs in charge_sessions),
        "total_charge_cost_usd": total_cost_usd,
        "mean_charge_duration_min": (sum(cs["duration_min"] for cs in charge_sessions) / len(charge_sessions)
                                      if charge_sessions else 0.0),
        "mission_flight_energy_wh": mission_flight_energy_wh,
        "session_log": charge_sessions,
        "mission_release_times": [m.release_time for m in missions],
        "mission_destinations": [m.destination for m in missions],
        "mission_deadlines": [m.deadline for m in missions],
        "request_times": request_times,
        "gate_binding_rate": (gate_refusals / gate_evaluations) if gate_evaluations > 0 else 0.0,
        "gate_evaluations": gate_evaluations,
        "gate_refusals": gate_refusals,
        "f12_Z": Z, "f12_cmax_term": cmax_term, "f12_energy_term": energy_term,
        "f12_tardy_term": tardy_term,
        "f12_makespan_capped_min": f12_makespan,
        "f12_tardiness_capped_min": f12_tardiness,
        "mean_on_pad_queue_length": on_pad_queue_ticks / final_t if final_t > 0 else 0.0,
        "runtime_per_decision_us": (dispatch_wall_time_s / len(request_times) * 1e6
                                     if request_times else 0.0),
        "dispatch_wall_time_s": dispatch_wall_time_s,
    }
    if policy == "ours":
        result["stampede_station_counts"] = stampede_station_counts
    return result


def _adaptive_target(uav: UAV, missions, t: float, dt_min: float) -> float:
    """Size the charge target to the most demanding mission releasing within
    LOOKAHEAD_MIN of now that this UAV could plausibly take (unassigned,
    reachable-by-energy from the station once charged to 100%). If none is
    on the horizon, top off fully -- no time pressure, avoids a near-term
    repeat trip (mirrors the reasoning in the exploratory PDF reports)."""
    horizon_t = t + LOOKAHEAD_MIN
    best_needed = None
    for m in missions:
        if m.assigned_uav is not None or m.completed_time is not None:
            continue
        if not (t <= m.release_time <= horizon_t):
            continue
        d = _distance(uav.position, m.destination)
        soc_needed = flight_energy_wh(d) / uav.battery_wh + SIGMA
        if soc_needed > 1.0:
            continue  # unreachable even at full charge; not this UAV's problem
        if best_needed is None or soc_needed > best_needed:
            best_needed = soc_needed
    if best_needed is None:
        return 1.0
    # Must clear the UAV's own recharge trigger, or it becomes IDLE still
    # below threshold and immediately re-enters charging next tick -- an
    # infinite zero-duration charge loop caught via a session-count blowup
    # (15000+ sessions for 15 drones) in the first version of this function.
    floor = RECHARGE_TRIGGER_SOC + 0.05
    return min(1.0, max(best_needed, floor))
