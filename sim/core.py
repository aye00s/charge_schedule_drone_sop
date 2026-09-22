"""Phase 2: discrete-event M/M/c/K simulator, used to validate Phase 1's
analytical model (Wang et al. 2020) before any assumption is relaxed.

Distributed layout: simulate_mmnm(lam/n, mu, n_servers=1, capacity=m, ...)
Concentrated layout: simulate_mmnm(lam, mu, n_servers=n, capacity=n*m, ...)
"""

import heapq
import math

import numpy as np


def simulate_mmnm(lam: float, mu: float, n_servers: int, capacity: int,
                   horizon: float, seed: int, warmup_frac: float = 0.1) -> dict:
    """Event-driven M/M/n_servers/capacity simulation.

    Returns a dict with:
      L          time-averaged number WAITING for a server (queue length,
                 excluding those already in service), post warm-up. This is
                 the reference paper's L (Eq. 11/13) -- confirmed empirically
                 against phase1_baseline; total-number-in-system does not
                 match.
      wait       mean queueing delay (time before service starts) of admitted
                 customers whose arrival occurred after warm-up
      block_frac fraction of post-warm-up arrivals blocked (system full)
    """
    rng = np.random.default_rng(seed)
    warmup_time = horizon * warmup_frac

    next_arrival = rng.exponential(1.0 / lam)
    departures = []  # min-heap of departure times for busy servers
    queue = []  # FIFO list of (arrival_time, counts_for_stats)

    n_in_system = 0
    busy = 0
    last_t = 0.0
    area = 0.0
    wait_sum = 0.0
    wait_count = 0
    arrivals_after_warmup = 0
    blocked_after_warmup = 0

    while True:
        next_departure = departures[0] if departures else math.inf
        t_next = min(next_arrival, next_departure)

        if t_next > horizon:
            seg_start = max(last_t, warmup_time)
            if seg_start < horizon:
                area += max(n_in_system - busy, 0) * (horizon - seg_start)
            break

        seg_start = max(last_t, warmup_time)
        if seg_start < t_next:
            area += max(n_in_system - busy, 0) * (t_next - seg_start)
        last_t = t_next

        if next_arrival <= next_departure:
            t = next_arrival
            counts = t >= warmup_time
            if counts:
                arrivals_after_warmup += 1
            if n_in_system < capacity:
                n_in_system += 1
                if busy < n_servers:
                    busy += 1
                    heapq.heappush(departures, t + rng.exponential(1.0 / mu))
                    if counts:
                        wait_count += 1  # wait = 0
                else:
                    queue.append((t, counts))
            else:
                if counts:
                    blocked_after_warmup += 1
            next_arrival = t + rng.exponential(1.0 / lam)
        else:
            t = heapq.heappop(departures)
            busy -= 1
            n_in_system -= 1
            if queue:
                arr_time, counts = queue.pop(0)
                busy += 1
                heapq.heappush(departures, t + rng.exponential(1.0 / mu))
                if counts:
                    wait_sum += (t - arr_time)
                    wait_count += 1

    duration = horizon - warmup_time
    L = area / duration
    mean_wait = wait_sum / wait_count if wait_count > 0 else 0.0
    block_frac = (blocked_after_warmup / arrivals_after_warmup
                  if arrivals_after_warmup > 0 else 0.0)
    return {"L": L, "wait": mean_wait, "block_frac": block_frac}
