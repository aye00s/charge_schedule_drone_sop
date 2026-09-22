"""Phase 6, remaining axes: station density (scarce/balanced/abundant),
mission load (light/nominal/saturated) independent of fleet size, and
tariff (flat/time-of-use) cost comparison. Fixed fleet size n=20 for the
density/load axes (sits right at the Phase 4/6 crossover zone found
earlier, a meaningful point to probe). 30 seeds, bootstrap CIs, paired
Wilcoxon where applicable.
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

SEEDS = list(range(1, 31))
N_UAVS = 20
HORIZON_MIN = 1000.0
AREA_SIDE = 2000.0


def stations_for(n_stations, seed=0):
    rng = np.random.default_rng(seed)
    return [tuple(p) for p in rng.uniform(0, AREA_SIDE, size=(n_stations, 2))]


def run_density_axis():
    print("=== Station density axis (n_uavs=20, mission_rate=0.8/min) ===", flush=True)
    rows = []
    for label, n_stations in [("scarce", 2), ("balanced", 5), ("abundant", 10)]:
        stations = stations_for(n_stations)
        full_e, adapt_e = [], []
        for seed in SEEDS:
            rf = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=2,
                                  horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=0.8,
                                  charge_policy="full", deadline_window_min=30.0)
            ra = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=2,
                                  horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=0.8,
                                  charge_policy="adaptive", deadline_window_min=30.0)
            full_e.append(rf["total_charge_energy_wh"])
            adapt_e.append(ra["total_charge_energy_wh"])
            rows.append({"axis": "density", "label": label, "n_stations": n_stations, "seed": seed,
                        "full_energy": rf["total_charge_energy_wh"], "adapt_energy": ra["total_charge_energy_wh"],
                        "full_safety": rf["safety_violations"], "adapt_safety": ra["safety_violations"]})
        mf, lof, hif = bootstrap_ci(full_e, seed=1)
        ma, loa, hia = bootstrap_ci(adapt_e, seed=1)
        pct = [(a - f) / f * 100 for a, f in zip(adapt_e, full_e)]
        mp, lop, hip = bootstrap_ci(pct, seed=1)
        stat, p = paired_test(adapt_e, full_e)
        print(f"{label} (n_stations={n_stations}): full={mf:.1f}[{lof:.1f},{hif:.1f}]  "
              f"adaptive={ma:.1f}[{loa:.1f},{hia:.1f}]  diff={mp:.2f}%[{lop:.2f},{hip:.2f}]  p={p:.2e}",
              flush=True)
    return rows


def run_load_axis():
    print("\n=== Mission-load axis (n_uavs=20, n_stations=5 fixed) ===", flush=True)
    stations = stations_for(5)
    rows = []
    for label, rate in [("light", 0.3), ("nominal", 0.8), ("saturated", 1.6)]:
        full_e, adapt_e = [], []
        for seed in SEEDS:
            rf = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=2,
                                  horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=rate,
                                  charge_policy="full", deadline_window_min=30.0)
            ra = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=2,
                                  horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=rate,
                                  charge_policy="adaptive", deadline_window_min=30.0)
            full_e.append(rf["total_charge_energy_wh"])
            adapt_e.append(ra["total_charge_energy_wh"])
            rows.append({"axis": "load", "label": label, "rate": rate, "seed": seed,
                        "full_energy": rf["total_charge_energy_wh"], "adapt_energy": ra["total_charge_energy_wh"],
                        "full_tardy": rf["tardy_count"], "adapt_tardy": ra["tardy_count"],
                        "full_completed": rf["missions_completed"], "adapt_completed": ra["missions_completed"]})
        mf, lof, hif = bootstrap_ci(full_e, seed=1)
        ma, loa, hia = bootstrap_ci(adapt_e, seed=1)
        pct = [(a - f) / f * 100 for a, f in zip(adapt_e, full_e)]
        mp, lop, hip = bootstrap_ci(pct, seed=1)
        stat, p = paired_test(adapt_e, full_e)
        print(f"{label} (rate={rate}): full={mf:.1f}[{lof:.1f},{hif:.1f}]  "
              f"adaptive={ma:.1f}[{loa:.1f},{hia:.1f}]  diff={mp:.2f}%[{lop:.2f},{hip:.2f}]  p={p:.2e}",
              flush=True)
    return rows


def run_tariff_axis():
    print("\n=== Tariff axis (n_uavs=20, n_stations=5, rate=0.8/min) ===", flush=True)
    stations = stations_for(5)
    rows = []
    for tariff in ["flat", "tou"]:
        for policy in ["full", "adaptive"]:
            costs = []
            for seed in SEEDS:
                r = run_mission_sim(n_uavs=N_UAVS, station_positions=stations, pads_per_station=2,
                                     horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=0.8,
                                     charge_policy=policy, tariff=tariff, deadline_window_min=30.0)
                costs.append(r["total_charge_cost_usd"])
                rows.append({"axis": "tariff", "tariff": tariff, "policy": policy, "seed": seed,
                            "cost_usd": r["total_charge_cost_usd"], "energy_wh": r["total_charge_energy_wh"]})
            mc, loc, hic = bootstrap_ci(costs, seed=1)
            print(f"tariff={tariff:4s} policy={policy:8s}  cost=${mc:.3f} [${loc:.3f},${hic:.3f}]", flush=True)
    return rows


def main():
    t0 = time.time()
    all_rows = run_density_axis() + run_load_axis() + run_tariff_axis()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase6_remaining_axes_{timestamp}.csv"
    # different row shapes per axis -- write each axis to its own section via union of fieldnames
    fieldnames = sorted(set().union(*[r.keys() for r in all_rows]))
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}")
    print(f"Elapsed: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
