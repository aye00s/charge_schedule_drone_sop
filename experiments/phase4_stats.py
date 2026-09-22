"""Phase 4, statistical rigor: 30-seed paired comparison of full vs adaptive
charging (the 4.4 finding), with bootstrap CIs and a Wilcoxon signed-rank
test, at two load levels."""

import csv
import datetime
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.mission_sim import run_mission_sim
from sim.stats import bootstrap_ci, paired_test

STATIONS_5 = [(300, 300), (1700, 300), (1000, 1000), (300, 1700), (1700, 1700)]
SEEDS = list(range(1, 31))


def main():
    t0 = time.time()
    rows = []
    for rate in [0.6, 1.2]:
        full_energy, adapt_energy = [], []
        full_completed, adapt_completed = [], []
        for seed in SEEDS:
            rf = run_mission_sim(n_uavs=15, station_positions=STATIONS_5, pads_per_station=2,
                                  horizon_min=1500, seed=seed, mission_rate_per_min=rate,
                                  charge_policy="full", deadline_window_min=30.0)
            ra = run_mission_sim(n_uavs=15, station_positions=STATIONS_5, pads_per_station=2,
                                  horizon_min=1500, seed=seed, mission_rate_per_min=rate,
                                  charge_policy="adaptive", deadline_window_min=30.0)
            full_energy.append(rf["total_charge_energy_wh"])
            adapt_energy.append(ra["total_charge_energy_wh"])
            full_completed.append(rf["missions_completed"])
            adapt_completed.append(ra["missions_completed"])
            rows.append({"rate": rate, "seed": seed, "full_energy": rf["total_charge_energy_wh"],
                         "adapt_energy": ra["total_charge_energy_wh"],
                         "full_safety_violations": rf["safety_violations"],
                         "adapt_safety_violations": ra["safety_violations"]})

        me_f, lo_f, hi_f = bootstrap_ci(full_energy, seed=1)
        me_a, lo_a, hi_a = bootstrap_ci(adapt_energy, seed=1)
        stat, p = paired_test(adapt_energy, full_energy)
        pct_diffs = [(a - f) / f * 100 for a, f in zip(adapt_energy, full_energy)]
        mpd, lopd, hipd = bootstrap_ci(pct_diffs, seed=1)

        print(f"rate={rate}", flush=True)
        print(f"  full energy:     {me_f:.1f} Wh  95% CI [{lo_f:.1f}, {hi_f:.1f}]")
        print(f"  adaptive energy: {me_a:.1f} Wh  95% CI [{lo_a:.1f}, {hi_a:.1f}]")
        print(f"  % diff (adaptive-full)/full: {mpd:.2f}%  95% CI [{lopd:.2f}%, {hipd:.2f}%]")
        print(f"  paired Wilcoxon p={p:.2e}  {'significant' if p < 0.05 else 'not significant'} (alpha=0.05)")
        print(f"  mean completed: full={sum(full_completed)/len(full_completed):.1f}  "
              f"adaptive={sum(adapt_completed)/len(adapt_completed):.1f}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase4_stats_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
