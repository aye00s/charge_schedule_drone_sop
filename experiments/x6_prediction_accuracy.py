"""REMEDIATION.md X6: prediction accuracy. 'Distribution of (predicted W_j
- realised wait) across all reservations in X3 runs. Expected to be zero
in the deterministic simulator; any spread must be explained.'

Uses the `prediction_error_min` field already logged on every 'ours'
session by sim/mission_sim.py (added 2026-09-22/23 during the F7
quantization fix and the priority-inversion diagnostics) -- re-runs X3's
own grid (5 configs x 30 layout/seed pairs) for the `ours` policy
specifically, since that field was never persisted to X3's original
summary-only CSV.
"""

import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.x3_baselines_vs_ours import CONFIGS, layout_seed_pairs, station_layout
from sim.mission_sim import run_mission_sim

N_UAVS = 20


def main():
    pairs = layout_seed_pairs(n_layouts=5, n_seeds_per_layout=6)
    assert len(pairs) == 30
    t0 = time.time()
    all_errors = []
    per_config_errors = {}
    for config_name, n_stations, mission_rate in CONFIGS:
        config_errors = []
        for layout_id, seed in pairs:
            stations = station_layout(n_stations, layout_seed=1000 + layout_id)
            r = run_mission_sim(policy="ours", n_uavs=N_UAVS, station_positions=stations,
                                 pads_per_station=2, horizon_min=1000.0, seed=seed,
                                 mission_rate_per_min=mission_rate, deadline_window_min=45.0,
                                 drain_cap_min=135.0)
            config_errors.extend(cs["prediction_error_min"] for cs in r["session_log"])
        per_config_errors[config_name] = config_errors
        all_errors.extend(config_errors)
        print(f"{config_name}: n_sessions={len(config_errors)}  "
              f"exact={sum(1 for e in config_errors if abs(e) < 1e-9)}  "
              f"nonzero={sum(1 for e in config_errors if abs(e) >= 1e-9)}  "
              f"elapsed={time.time()-t0:.1f}s", flush=True)

    print(f"\n=== X6 overall (5 X3 configs x 30 pairs, policy='ours', default F9) ===")
    n = len(all_errors)
    exact = sum(1 for e in all_errors if abs(e) < 1e-9)
    print(f"total reservations (completed sessions) = {n}")
    print(f"exact matches (error == 0)              = {exact}")
    print(f"nonzero                                 = {n - exact}")
    if n - exact > 0:
        nonzero = [e for e in all_errors if abs(e) >= 1e-9]
        print(f"nonzero min={min(nonzero)} max={max(nonzero)} mean={np.mean(nonzero):.6f}")
        c = Counter(round(e, 4) for e in nonzero)
        print("most common nonzero values:", c.most_common(10))
    print(f"\nTotal elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
