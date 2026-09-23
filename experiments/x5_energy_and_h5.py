"""REMEDIATION.md X5: energy and H5, done properly. Repeats the Phase 6
fleet/density/load sweeps for full vs partial charging, decomposes energy
into its three real components, normalises per completed mission, and
tests H5 (makespan, miss rate) directly -- H5 was never actually tested
before (E12/HISTORY.md): only total energy was measured, and total energy
is not what H5 predicts.

Design (2026-09-23):
- 4 policy variants: ours+partial (use_partial=True, the "adaptive"-style
  policy for the modern heuristic), ours+full (use_partial=False), and
  the original baseline's own full/adaptive charge_policy pair (kept for
  continuity with the original Phase 4/6 comparison, per REMEDIATION.md's
  explicit "and the old adaptive policy for continuity").
- 3 sweep axes, each varying ONE thing with the others held at a shared
  centre point (n_uavs=20, n_stations=5, rate=0.8), never fleet size and
  drones-per-station at once:
  - fleet size: n_uavs in {12, 20, 40}, n_stations = n_uavs/4 (drones-
    per-station FIXED at 4, per the user's explicit instruction).
  - station density: n_stations in {2 (scarce), 5 (balanced), 10 (abundant)},
    n_uavs=20 fixed, pads_per_station=2 fixed.
  - mission load: mission_rate in {0.3 (light), 0.8 (nominal), 1.6 (saturated)},
    n_uavs=20, n_stations=5 fixed.
  8 unique configs total (the centre point is shared by all three axes).
- >=5 random layouts per configuration: 5 layouts x 6 seeds = 30 pairs,
  same convention as X3/X4, every policy on the same pairs.
- Energy decomposition (all three fields already logged by
  sim/mission_sim.py): mission_flight_energy_wh, station_trip_energy_wh,
  end_of_run_stored_charge_change_wh -- normalised by missions_completed.
- H5 metrics: makespan_min and miss_rate, full vs partial (both engines).

Usage: `python experiments/x5_energy_and_h5.py --pilot` for a small
timing/correctness check; no flag for the full run.
"""

import argparse
import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.mission_sim import run_mission_sim

DEADLINE_WINDOW_MIN = 45.0
DRAIN_CAP_MIN = 3 * DEADLINE_WINDOW_MIN
AREA_SIDE_M = 2000.0
PADS_PER_STATION = 2
HORIZON_MIN = 1000.0

CENTRE = dict(n_uavs=20, n_stations=5, mission_rate=0.8)

CONFIGS = [
    ("fleet_12", dict(n_uavs=12, n_stations=3, mission_rate=CENTRE["mission_rate"])),
    ("fleet_20_centre", dict(n_uavs=20, n_stations=5, mission_rate=CENTRE["mission_rate"])),
    ("fleet_40", dict(n_uavs=40, n_stations=10, mission_rate=CENTRE["mission_rate"])),
    ("density_scarce", dict(n_uavs=20, n_stations=2, mission_rate=CENTRE["mission_rate"])),
    ("density_abundant", dict(n_uavs=20, n_stations=10, mission_rate=CENTRE["mission_rate"])),
    ("load_light", dict(n_uavs=20, n_stations=5, mission_rate=0.3)),
    ("load_saturated", dict(n_uavs=20, n_stations=5, mission_rate=1.6)),
]
# fleet_20_centre / density_balanced(=fleet_20_centre) / load_nominal(=fleet_20_centre)
# are the same run -- included once, not three times.

POLICIES = [
    ("ours_partial", dict(policy="ours", use_partial=True)),
    ("ours_full", dict(policy="ours", use_partial=False)),
    ("baseline_adaptive", dict(policy="baseline", charge_policy="adaptive")),
    ("baseline_full", dict(policy="baseline", charge_policy="full")),
]


def station_layout(n_stations, layout_id):
    rng = np.random.default_rng(2000 + layout_id * 100 + n_stations)
    return [tuple(rng.uniform(0, AREA_SIDE_M, size=2)) for _ in range(n_stations)]


def layout_seed_pairs(n_layouts=5, n_seeds_per_layout=6):
    pairs = []
    seed = 1
    for layout_id in range(n_layouts):
        for _ in range(n_seeds_per_layout):
            pairs.append((layout_id, seed))
            seed += 1
    return pairs


def run_one(policy_kwargs, n_uavs, n_stations, mission_rate, layout_id, seed):
    stations = station_layout(n_stations, layout_id)
    r = run_mission_sim(n_uavs=n_uavs, station_positions=stations, pads_per_station=PADS_PER_STATION,
                         horizon_min=HORIZON_MIN, seed=seed, mission_rate_per_min=mission_rate,
                         deadline_window_min=DEADLINE_WINDOW_MIN, drain_cap_min=DRAIN_CAP_MIN,
                         **policy_kwargs)
    nc = max(1, r["missions_completed"])  # avoid div-by-zero; flagged separately if 0
    r["mission_flight_energy_per_completed_wh"] = r["mission_flight_energy_wh"] / nc
    r["station_trip_energy_per_completed_wh"] = r["station_trip_energy_wh"] / nc
    r["stored_charge_change_per_completed_wh"] = r["end_of_run_stored_charge_change_wh"] / nc
    r["miss_rate"] = r["tardy_count"] / r["missions_total"] if r["missions_total"] > 0 else 0.0
    return r


def run_pilot():
    pairs = [(0, 1), (0, 2)]
    config_name, cfg = CONFIGS[1]  # fleet_20_centre
    print(f"PILOT: config={config_name} {cfg}, pairs={pairs}\n")
    t0 = time.time()
    rows = []
    for policy_name, kwargs in POLICIES:
        for layout_id, seed in pairs:
            rt0 = time.time()
            r = run_one(kwargs, cfg["n_uavs"], cfg["n_stations"], cfg["mission_rate"], layout_id, seed)
            rt = time.time() - rt0
            rows.append(dict(policy=policy_name, layout_id=layout_id, seed=seed, runtime_s=rt,
                              missions_completed=r["missions_completed"], missions_total=r["missions_total"],
                              makespan_min=r["makespan_min"], miss_rate=r["miss_rate"],
                              mission_flight_per=r["mission_flight_energy_per_completed_wh"],
                              station_trip_per=r["station_trip_energy_per_completed_wh"],
                              stored_change_per=r["stored_charge_change_per_completed_wh"],
                              safety=r["safety_violations"]))
            print(f"{policy_name:20s} layout={layout_id} seed={seed} runtime={rt:.3f}s "
                  f"completed={r['missions_completed']}/{r['missions_total']} makespan={r['makespan_min']:.1f} "
                  f"miss_rate={r['miss_rate']:.3f} mission_E/mis={r['mission_flight_energy_per_completed_wh']:.3f} "
                  f"station_E/mis={r['station_trip_energy_per_completed_wh']:.3f} "
                  f"stored_dE/mis={r['stored_charge_change_per_completed_wh']:.4f} safety={r['safety_violations']}",
                  flush=True)
    total_s = time.time() - t0
    n_runs = len(rows)
    print(f"\nPilot: {n_runs} runs in {total_s:.1f}s ({total_s/n_runs:.3f}s/run average)")
    full_n_runs = len(POLICIES) * len(CONFIGS) * 30
    est_s = full_n_runs * (total_s / n_runs)
    print(f"Full X5: {len(POLICIES)} policies x {len(CONFIGS)} configs x 30 pairs = {full_n_runs} runs. "
          f"Estimated: {est_s/60:.1f} min ({est_s:.0f}s)")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x5_pilot_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {n_runs} rows to {out_path}")


def run_full():
    pairs = layout_seed_pairs()
    assert len(pairs) == 30
    total_runs = len(POLICIES) * len(CONFIGS) * len(pairs)
    print(f"Full X5: {len(POLICIES)} policies x {len(CONFIGS)} configs x {len(pairs)} pairs = {total_runs} runs")
    t0 = time.time()
    all_rows = []
    for config_name, cfg in CONFIGS:
        for policy_name, kwargs in POLICIES:
            for layout_id, seed in pairs:
                r = run_one(kwargs, cfg["n_uavs"], cfg["n_stations"], cfg["mission_rate"], layout_id, seed)
                all_rows.append(dict(
                    config=config_name, policy=policy_name, layout_id=layout_id, seed=seed,
                    n_uavs=cfg["n_uavs"], n_stations=cfg["n_stations"], mission_rate=cfg["mission_rate"],
                    missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                    unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                    makespan_min=r["makespan_min"],
                    mission_flight_energy_wh=r["mission_flight_energy_wh"],
                    station_trip_energy_wh=r["station_trip_energy_wh"],
                    end_of_run_stored_charge_change_wh=r["end_of_run_stored_charge_change_wh"],
                    mission_flight_energy_per_completed_wh=r["mission_flight_energy_per_completed_wh"],
                    station_trip_energy_per_completed_wh=r["station_trip_energy_per_completed_wh"],
                    stored_charge_change_per_completed_wh=r["stored_charge_change_per_completed_wh"],
                    total_charge_energy_ticked_wh=r["total_charge_energy_ticked_wh"],
                    safety_violations=r["safety_violations"], charge_sessions=r["charge_sessions"],
                ))
        print(f"  config={config_name} done, elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x5_full_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    print("\n=== H5 test: makespan and miss rate, full vs partial (mean across 30 pairs) ===")
    for config_name, _ in CONFIGS:
        print(f"\n{config_name}:")
        for pair in [("ours_partial", "ours_full"), ("baseline_adaptive", "baseline_full")]:
            a_rows = [r for r in all_rows if r["config"] == config_name and r["policy"] == pair[0]]
            b_rows = [r for r in all_rows if r["config"] == config_name and r["policy"] == pair[1]]
            a_makespan = np.mean([r["makespan_min"] for r in a_rows])
            b_makespan = np.mean([r["makespan_min"] for r in b_rows])
            a_miss = np.mean([r["miss_rate"] for r in a_rows])
            b_miss = np.mean([r["miss_rate"] for r in b_rows])
            print(f"  {pair[0]:20s} makespan={a_makespan:7.2f} miss={a_miss:.4f}   "
                  f"{pair[1]:20s} makespan={b_makespan:7.2f} miss={b_miss:.4f}")

    print("\n=== Energy decomposition, per completed mission (mean across 30 pairs) ===")
    for config_name, _ in CONFIGS:
        print(f"\n{config_name}:")
        for policy_name, _ in POLICIES:
            rows = [r for r in all_rows if r["config"] == config_name and r["policy"] == policy_name]
            mf = np.mean([r["mission_flight_energy_per_completed_wh"] for r in rows])
            st = np.mean([r["station_trip_energy_per_completed_wh"] for r in rows])
            sc = np.mean([r["stored_charge_change_per_completed_wh"] for r in rows])
            print(f"  {policy_name:20s} mission_flight/mis={mf:7.3f}  station_trip/mis={st:7.3f}  "
                  f"stored_charge_change/mis={sc:8.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.pilot:
        run_pilot()
    else:
        run_full()
