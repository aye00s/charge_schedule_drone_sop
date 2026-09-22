"""Phase 6: fleet-size scaling sweep (Section 8's sweep table), 30 seeds
per configuration, comparing full vs adaptive charging with bootstrap CIs,
paired Wilcoxon tests, and wall-clock runtime scaling.

Scope note (reported honestly, not silently limited): this covers the
fleet-size axis with >=30 seeds, CIs, and paired tests as specified. It does
NOT cover the tariff (flat/time-of-use) or discrete station-density
(scarce/balanced/abundant) axes from Section 8's table -- those require
tariff-cost modeling and multiple density configs per fleet size that don't
exist in the current model and would be a new feature, not a statistics
pass. Station count is scaled with fleet size (roughly 1 station per 4
drones, 2 pads each) as a single "balanced" density setting.
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.mission_sim import run_mission_sim
from sim.stats import bootstrap_ci, paired_test

FLEET_SIZES = [5, 10, 20, 40, 60]
SEEDS = list(range(1, 31))
AREA_SIDE = 2000.0
HORIZON_MIN = 1000.0


def station_positions_for(n_uavs, seed=0):
    n_stations = max(2, round(n_uavs / 4))
    rng = np.random.default_rng(seed)  # fixed layout per fleet size, independent of run seed
    return [tuple(p) for p in rng.uniform(0, AREA_SIDE, size=(n_stations, 2))]


def main():
    t0 = time.time()
    rows = []
    summary = []

    for n_uavs in FLEET_SIZES:
        stations = station_positions_for(n_uavs)
        mission_rate = 0.04 * n_uavs
        full_energy, adapt_energy = [], []
        full_completed, adapt_completed = [], []
        full_runtime, adapt_runtime = [], []

        for seed in SEEDS:
            t_a = time.time()
            rf = run_mission_sim(n_uavs=n_uavs, station_positions=stations, pads_per_station=2,
                                  horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                                  charge_policy="full", deadline_window_min=30.0)
            t_full = time.time() - t_a

            t_a = time.time()
            ra = run_mission_sim(n_uavs=n_uavs, station_positions=stations, pads_per_station=2,
                                  horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                                  charge_policy="adaptive", deadline_window_min=30.0)
            t_adapt = time.time() - t_a

            full_energy.append(rf["total_charge_energy_wh"])
            adapt_energy.append(ra["total_charge_energy_wh"])
            full_completed.append(rf["missions_completed"])
            adapt_completed.append(ra["missions_completed"])
            full_runtime.append(t_full)
            adapt_runtime.append(t_adapt)

            rows.append({"n_uavs": n_uavs, "n_stations": len(stations), "seed": seed,
                        "full_energy": rf["total_charge_energy_wh"], "adapt_energy": ra["total_charge_energy_wh"],
                        "full_completed": rf["missions_completed"], "adapt_completed": ra["missions_completed"],
                        "full_safety_violations": rf["safety_violations"],
                        "adapt_safety_violations": ra["safety_violations"],
                        "full_runtime_s": t_full, "adapt_runtime_s": t_adapt})

        n_ticks = int(HORIZON_MIN)  # dt=1min
        decisions_per_run = n_uavs * n_ticks
        mean_full_rt = np.mean(full_runtime)
        mean_adapt_rt = np.mean(adapt_runtime)
        per_decision_us = (mean_full_rt / decisions_per_run) * 1e6

        me_f, lo_f, hi_f = bootstrap_ci(full_energy, seed=1)
        me_a, lo_a, hi_a = bootstrap_ci(adapt_energy, seed=1)
        stat, p = paired_test(adapt_energy, full_energy)
        pct_diffs = [(a - f) / f * 100 for a, f in zip(adapt_energy, full_energy)]
        mpd, lopd, hipd = bootstrap_ci(pct_diffs, seed=1)
        total_safety = sum(full_completed) * 0  # placeholder, safety already tracked

        print(f"n_uavs={n_uavs} n_stations={len(stations)}", flush=True)
        print(f"  full energy: {me_f:.1f} [{lo_f:.1f},{hi_f:.1f}]  "
              f"adaptive: {me_a:.1f} [{lo_a:.1f},{hi_a:.1f}]")
        print(f"  %% diff (adaptive-full)/full: {mpd:.2f}%% [{lopd:.2f}%%, {hipd:.2f}%%]  "
              f"p={p:.2e} {'sig' if p < 0.05 else 'not sig'}")
        print(f"  mean runtime/run: full={mean_full_rt*1000:.1f}ms  adaptive={mean_adapt_rt*1000:.1f}ms  "
              f"per-decision~{per_decision_us:.3f}us")
        print(f"  safety violations: full={sum(rf['safety_violations'] for rf in [rf])}  "
              f"(all seeds: full total={sum(r['full_safety_violations'] for r in rows if r['n_uavs']==n_uavs)}, "
              f"adaptive total={sum(r['adapt_safety_violations'] for r in rows if r['n_uavs']==n_uavs)})")

        summary.append({
            "n_uavs": n_uavs, "n_stations": len(stations),
            "full_energy_mean": me_f, "adapt_energy_mean": me_a,
            "pct_diff_mean": mpd, "pct_diff_lo": lopd, "pct_diff_hi": hipd,
            "wilcoxon_p": p, "mean_runtime_full_ms": mean_full_rt * 1000,
            "mean_runtime_adapt_ms": mean_adapt_rt * 1000,
        })

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase6_scale_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary_path = ROOT / "results" / f"phase6_scale_summary_{timestamp}.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Wrote summary to {summary_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
