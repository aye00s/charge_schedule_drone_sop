"""Phase 3: n-station distributed-layout simulator with configurable service
order and pad-routing policy, used to compare regimes R1/R2/R3a against the
Phase 1/2 analytical and simulated baselines.

Each station is a single-server M/M/1/m queue (n stations total, matching
the reference paper's distributed layout). What varies by regime:
  routing: 'fixed_split'  -- each arrival picks a station uniformly at random
                             (statistically equivalent to n independent
                             lambda/n streams -- the paper's assumption)
           'jsq'           -- scheduler routes to the station with the fewest
                             drones currently WAITING (a stand-in for the
                             deterministic W_j(t) of Section 5.2; no travel
                             or energy model exists yet to do better)
           'jsq_travel'    -- R3b: adds travel time to the routing cost,
                             J_ij = n_in_system[j]/mu + dist(origin,j)/speed/60
                             (minutes; Section 5.1's time-only cost
                             combination, sans T^chg which doesn't exist
                             until Phase 4). REMEDIATION.md E4: routing by
                             in-system count (not waiting-only, E3), cost
                             genuinely in minutes (mu is calibrated as
                             "services per minute" once travel is in the
                             picture), and -- the substantive fix -- a
                             routed request no longer joins the pad
                             instantly. It is scheduled as a separate event
                             at t + travel_time_minutes, exactly like a
                             drone that is actually flying there; only once
                             that event fires does it occupy a slot /
                             affect L, block, or queue-order decisions.
                             Geometry is an open decision (Section 13 #6)
                             that was not settled with the user; a default
                             was picked to proceed: n stations at fixed
                             positions drawn once (station_seed=0) uniform
                             in a 2000m x 2000m area, drone speed 15 m/s,
                             each request's origin drawn uniform in the same
                             area. Revisit if the user specifies otherwise.
  order:   'fcfs'          -- serve in arrival order
           'priority'      -- serve in order of earliest deadline
                             (arrival_time + slack); with slack independent
                             of service duration, Kleinrock's conservation
                             law says average L and wait must be unaffected

Every request draws a slack value regardless of regime, so runs sharing a
seed are directly comparable (common random numbers).
"""

import heapq
import math

import numpy as np


AREA_SIDE_M = 2000.0
DRONE_SPEED_MPS = 15.0
STATION_LAYOUT_SEED = 0


def _station_positions(n_stations, layout_seed: int = STATION_LAYOUT_SEED):
    rng = np.random.default_rng(layout_seed)
    return rng.uniform(0.0, AREA_SIDE_M, size=(n_stations, 2))


def simulate_regime(routing: str, order: str, n_stations: int, capacity: int,
                     lam_total: float, mu: float, horizon: float, seed: int,
                     slack_mean: float = 0.0, warmup_frac: float = 0.1,
                     layout_seed: int = STATION_LAYOUT_SEED) -> dict:
    """Returns a dict with:
      L           mean per-station time-averaged queue length (waiting only,
                  excluding those in service) -- same definition as
                  sim.core.simulate_mmnm, averaged across the n stations
      wait        mean ON-PAD queueing delay of admitted requests (post
                  warm-up), rescaled by lam_total (paper's "1/lambda
                  factored out"). Does NOT include travel time -- this is
                  the quantity validated against the Phase 1/2 analytics.
      total_delay mean delay from request time to service start, INCLUDING
                  travel time where routing has any (jsq_travel). Not
                  rescaled by lam_total. REMEDIATION.md E4(c)'s accounting
                  rule: moving waiting off the pad (via travel) must never
                  make it disappear from the metrics -- report both.
      block_frac  fraction of post-warm-up arrivals blocked
      within_window  fraction of admitted, post-warm-up requests whose
                     service started at or before their deadline (only
                     meaningful when slack_mean > 0)
    """
    assert routing in ("fixed_split", "jsq", "jsq_travel")
    assert order in ("fcfs", "priority")

    rng = np.random.default_rng(seed)
    # REMEDIATION.md E3: tie-breaking uses a SEPARATE RNG stream, derived
    # deterministically from `seed` but never drawn from `rng` itself, so it
    # never disturbs the arrival/service/slack draws -- otherwise CRN
    # comparisons between routing policies (which tie-break differently, or
    # differently often) would silently desync the underlying random
    # realization. `rng`'s own construction is untouched so every previously
    # validated result (R1 vs analytics, conservation check, etc., none of
    # which ever tie-break) remains bit-for-bit reproducible.
    tie_rng = np.random.default_rng(seed * 1_000_003 + 7919)
    warmup_time = horizon * warmup_frac
    station_pos = _station_positions(n_stations, layout_seed) if routing == "jsq_travel" else None

    n_in_system = [0] * n_stations
    busy = [False] * n_stations
    queues = [[] for _ in range(n_stations)]  # list (fcfs) or heap (priority)
    departures = []  # global heap of (time, station)
    # REMEDIATION.md E4(c): a routed request is no longer admitted the
    # instant it's routed -- it's scheduled as a "pad arrival" event at
    # t + travel_time, exactly like a drone that is actually flying there.
    # For fixed_split/jsq, travel_time is always 0, so this event fires on
    # the very next loop iteration with no intervening event (negligible
    # chance of an exact tie with a departure), reproducing the old
    # instant-admission behavior exactly for those two routings.
    pad_arrivals = []  # heap of (arrival_time, station, request_time, deadline, counts)

    next_request = rng.exponential(1.0 / lam_total)
    last_t = 0.0
    area = 0.0
    wait_sum = 0.0
    wait_count = 0
    on_time_count = 0
    arrivals_after_warmup = 0
    blocked_after_warmup = 0
    total_delay_sum = 0.0  # includes travel time (E4(c)'s accounting rule)
    total_delay_count = 0

    def waiting_count(j):
        return n_in_system[j] - (1 if busy[j] else 0)

    def argmin_tiebreak(values):
        """REMEDIATION.md E3: an idle pad (0 waiting, 0 in system) and a
        busy pad with an empty queue (0 waiting, 1 in system) both scored 0
        under waiting-count routing, so an arrival could be sent to the
        busy pad while another sat idle. Route by IN-SYSTEM count instead
        (the actual congestion measure), with ties broken uniformly at
        random on the separate tie_rng stream."""
        values = np.asarray(values)
        best = values.min()
        candidates = np.flatnonzero(values == best)
        if len(candidates) == 1:
            return int(candidates[0])
        return int(candidates[tie_rng.integers(len(candidates))])

    while True:
        next_pad_arrival = pad_arrivals[0][0] if pad_arrivals else math.inf
        next_departure = departures[0][0] if departures else math.inf
        t_next = min(next_request, next_pad_arrival, next_departure)

        if t_next > horizon:
            seg_start = max(last_t, warmup_time)
            if seg_start < horizon:
                total_waiting = sum(waiting_count(j) for j in range(n_stations))
                area += total_waiting * (horizon - seg_start)
            break

        seg_start = max(last_t, warmup_time)
        if seg_start < t_next:
            total_waiting = sum(waiting_count(j) for j in range(n_stations))
            area += total_waiting * (t_next - seg_start)
        last_t = t_next

        if next_request <= next_pad_arrival and next_request <= next_departure:
            # REQUEST event: decide routing now, schedule pad arrival later.
            t = next_request
            slack = rng.exponential(slack_mean) if slack_mean > 0 else 0.0
            deadline = t + slack

            if routing == "fixed_split":
                j = rng.integers(n_stations)
                travel_time = 0.0
            elif routing == "jsq":
                j = argmin_tiebreak([n_in_system[k] for k in range(n_stations)])
                travel_time = 0.0
            else:  # jsq_travel
                origin = rng.uniform(0.0, AREA_SIDE_M, size=2)
                travel_time_minutes = (np.linalg.norm(station_pos - origin, axis=1)
                                        / DRONE_SPEED_MPS / 60.0)
                cost = np.array([n_in_system[k] for k in range(n_stations)]) / mu + travel_time_minutes
                j = argmin_tiebreak(cost)
                travel_time = float(travel_time_minutes[j])

            heapq.heappush(pad_arrivals, (t + travel_time, j, t, deadline, t >= warmup_time))
            next_request = t + rng.exponential(1.0 / lam_total)

        elif next_pad_arrival <= next_departure:
            # PAD ARRIVAL event: the old "arrival" logic, now decoupled
            # from the routing decision by travel_time.
            t, j, request_time, deadline, counts = heapq.heappop(pad_arrivals)
            if counts:
                arrivals_after_warmup += 1

            if n_in_system[j] < capacity:
                n_in_system[j] += 1
                if not busy[j]:
                    busy[j] = True
                    dep_t = t + rng.exponential(1.0 / mu)
                    heapq.heappush(departures, (dep_t, j))
                    if counts:
                        wait_count += 1
                        on_time_count += 1  # on-pad wait = 0, always on time
                        total_delay_sum += (t - request_time)  # travel only, no queueing
                        total_delay_count += 1
                else:
                    if order == "fcfs":
                        queues[j].append((t, deadline, counts, request_time))
                    else:
                        heapq.heappush(queues[j], (deadline, t, counts, request_time))
            else:
                if counts:
                    blocked_after_warmup += 1
        else:
            t, j = heapq.heappop(departures)
            busy[j] = False
            n_in_system[j] -= 1
            if queues[j]:
                if order == "fcfs":
                    arr_time, deadline, counts, request_time = queues[j].pop(0)
                else:
                    deadline, arr_time, counts, request_time = heapq.heappop(queues[j])
                busy[j] = True
                dep_t = t + rng.exponential(1.0 / mu)
                heapq.heappush(departures, (dep_t, j))
                if counts:
                    wait_sum += (t - arr_time)  # on-pad queueing delay only
                    wait_count += 1
                    total_delay_sum += (t - request_time)  # E4(c): includes travel
                    total_delay_count += 1
                    if t <= deadline:
                        on_time_count += 1

    duration = horizon - warmup_time
    L = (area / duration) / n_stations
    mean_wait = wait_sum / wait_count if wait_count > 0 else 0.0
    mean_total_delay = total_delay_sum / total_delay_count if total_delay_count > 0 else 0.0
    block_frac = (blocked_after_warmup / arrivals_after_warmup
                  if arrivals_after_warmup > 0 else 0.0)
    within_window = on_time_count / wait_count if wait_count > 0 else 1.0
    return {"L": L, "wait": mean_wait, "total_delay": mean_total_delay,
            "block_frac": block_frac, "within_window": within_window}


def simulate_concentrated_with_travel(n_servers: int, capacity: int, lam_total: float,
                                       mu: float, horizon: float, seed: int,
                                       hub_position: tuple, order: str = "fcfs",
                                       slack_mean: float = 0.0, warmup_frac: float = 0.1,
                                       area_side: float = AREA_SIDE_M,
                                       drone_speed_mps: float = DRONE_SPEED_MPS) -> dict:
    """REMEDIATION.md E4(d): R3b (jsq_travel, distributed + travel-aware
    routing) was being compared against L_c_analytic, a concentrated
    baseline with NO travel modeled at all -- changing two things at once
    (routing/pooling AND travel). This is the missing like-for-like
    baseline: one hub (n_servers parallel pads, capacity n_servers*m,
    matching the standard concentrated setup) that ALSO makes every
    request travel from a random origin to the hub before joining the
    queue, using the exact same event-scheduled-arrival mechanism as
    simulate_regime's jsq_travel. hub_position is the caller's choice (E4d
    default: centroid of the distributed layout's station positions, so
    the two regimes being compared share a coherent geometry)."""
    rng = np.random.default_rng(seed)
    warmup_time = horizon * warmup_frac

    n_in_system = 0
    busy_count = 0
    queue = []  # list (fcfs) or heap (priority)
    departures = []  # heap of departure times (single station)
    pad_arrivals = []  # heap of (arrival_time, request_time, deadline, counts)

    next_request = rng.exponential(1.0 / lam_total)
    last_t = 0.0
    area = 0.0
    wait_sum = 0.0
    wait_count = 0
    on_time_count = 0
    arrivals_after_warmup = 0
    blocked_after_warmup = 0
    total_delay_sum = 0.0
    total_delay_count = 0

    while True:
        next_pad_arrival = pad_arrivals[0][0] if pad_arrivals else math.inf
        next_departure = departures[0] if departures else math.inf
        t_next = min(next_request, next_pad_arrival, next_departure)

        if t_next > horizon:
            seg_start = max(last_t, warmup_time)
            if seg_start < horizon:
                area += max(n_in_system - busy_count, 0) * (horizon - seg_start)
            break

        seg_start = max(last_t, warmup_time)
        if seg_start < t_next:
            area += max(n_in_system - busy_count, 0) * (t_next - seg_start)
        last_t = t_next

        if next_request <= next_pad_arrival and next_request <= next_departure:
            t = next_request
            slack = rng.exponential(slack_mean) if slack_mean > 0 else 0.0
            deadline = t + slack
            origin = rng.uniform(0.0, area_side, size=2)
            travel_time = math.hypot(origin[0] - hub_position[0], origin[1] - hub_position[1]) \
                / drone_speed_mps / 60.0
            heapq.heappush(pad_arrivals, (t + travel_time, t, deadline, t >= warmup_time))
            next_request = t + rng.exponential(1.0 / lam_total)

        elif next_pad_arrival <= next_departure:
            t, request_time, deadline, counts = heapq.heappop(pad_arrivals)
            if counts:
                arrivals_after_warmup += 1
            if n_in_system < capacity:
                n_in_system += 1
                if busy_count < n_servers:
                    busy_count += 1
                    dep_t = t + rng.exponential(1.0 / mu)
                    heapq.heappush(departures, dep_t)
                    if counts:
                        wait_count += 1
                        on_time_count += 1
                        total_delay_sum += (t - request_time)
                        total_delay_count += 1
                else:
                    if order == "fcfs":
                        queue.append((t, deadline, counts, request_time))
                    else:
                        heapq.heappush(queue, (deadline, t, counts, request_time))
            else:
                if counts:
                    blocked_after_warmup += 1
        else:
            t = heapq.heappop(departures)
            busy_count -= 1
            n_in_system -= 1
            if queue:
                if order == "fcfs":
                    arr_time, deadline, counts, request_time = queue.pop(0)
                else:
                    deadline, arr_time, counts, request_time = heapq.heappop(queue)
                busy_count += 1
                dep_t = t + rng.exponential(1.0 / mu)
                heapq.heappush(departures, dep_t)
                if counts:
                    wait_sum += (t - arr_time)
                    wait_count += 1
                    total_delay_sum += (t - request_time)
                    total_delay_count += 1
                    if t <= deadline:
                        on_time_count += 1

    duration = horizon - warmup_time
    L = area / duration
    mean_wait = wait_sum / wait_count if wait_count > 0 else 0.0
    mean_total_delay = total_delay_sum / total_delay_count if total_delay_count > 0 else 0.0
    block_frac = (blocked_after_warmup / arrivals_after_warmup
                  if arrivals_after_warmup > 0 else 0.0)
    within_window = on_time_count / wait_count if wait_count > 0 else 1.0
    return {"L": L, "wait": mean_wait, "total_delay": mean_total_delay,
            "block_frac": block_frac, "within_window": within_window}


def centroid(positions) -> tuple:
    arr = np.asarray(positions)
    return (float(arr[:, 0].mean()), float(arr[:, 1].mean()))
