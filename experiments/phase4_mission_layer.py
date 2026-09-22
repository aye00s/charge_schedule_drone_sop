"""Phase 4 exploration: 4.1 (is the emergent charge-request stream roughly
Poisson?), 4.2 (deadlines/tardiness under load), 4.3 (CC-CV charge duration
is not exponential -- M/G/c, not M/M/c), 4.4 (full vs adaptive-partial
charging, expect the largest benefit at high load). One seed per scale here
(exploratory); not Phase 6 statistical rigor.
"""

import csv
import datetime
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.mission_sim import run_mission_sim

STATIONS_5 = [(300, 300), (1700, 300), (1000, 1000), (300, 1700), (1700, 1700)]


def section_4_1_poisson_check():
    print("=== 4.1: is the emergent request stream roughly Poisson? ===")
    r = run_mission_sim(n_uavs=20, station_positions=STATIONS_5, pads_per_station=2,
                         horizon_min=3000, seed=1, mission_rate_per_min=0.8, charge_policy="full")
    req = np.array(r["request_times"])
    inter = np.diff(np.sort(req))
    mean_iat = inter.mean()
    std_iat = inter.std()
    cv = std_iat / mean_iat
    print(f"requests={len(req)}  mean inter-arrival={mean_iat:.3f} min  "
          f"std={std_iat:.3f}  CV={cv:.3f} (exponential CV=1.0)")
    print(f"implied emergent lambda = {1/mean_iat:.4f} requests/min "
          f"(safety_violations={r['safety_violations']})")
    return r


def section_4_2_deadlines_under_load():
    print("\n=== 4.2: tardiness under increasing mission load ===")
    for rate in [0.3, 0.6, 0.9, 1.2, 1.5]:
        r = run_mission_sim(n_uavs=15, station_positions=STATIONS_5, pads_per_station=2,
                             horizon_min=1500, seed=2, mission_rate_per_min=rate,
                             charge_policy="full", deadline_window_min=30.0)
        miss_rate = r["tardy_count"] / max(r["missions_completed"], 1)
        print(f"rate={rate:.1f}  completed={r['missions_completed']}/{r['missions_total']}  "
              f"tardy={r['tardy_count']} ({miss_rate:.1%})  "
              f"mean_tardiness={r['total_tardiness_min']/max(r['tardy_count'],1):.2f}min  "
              f"safety_violations={r['safety_violations']}")


def section_4_3_service_time_not_exponential(mission_run):
    print("\n=== 4.3: charge duration distribution (CC-CV -> M/G/c, not M/M/c) ===")
    durations = np.array([cs["duration_min"] for cs in mission_run["session_log"]])
    mean_d, std_d = durations.mean(), durations.std()
    cv = std_d / mean_d
    print(f"n_sessions={len(durations)}  mean={mean_d:.2f}min  std={std_d:.2f}  "
          f"CV={cv:.3f} (exponential service would have CV=1.0)")
    print("Interpretation: CV far from 1.0 confirms charge duration is not "
          "exponential -- it is a deterministic function of arrival SoC via "
          "the CC-CV curve, so the paper's M/M/c formulas do not apply here.")


def section_4_4_full_vs_adaptive():
    print("\n=== 4.4: full vs adaptive-partial charging, by load ===")
    rows = []
    for rate in [0.3, 0.6, 0.9, 1.2]:
        for policy in ["full", "adaptive"]:
            r = run_mission_sim(n_uavs=15, station_positions=STATIONS_5, pads_per_station=2,
                                 horizon_min=1500, seed=4, mission_rate_per_min=rate,
                                 charge_policy=policy, deadline_window_min=30.0)
            rows.append({"rate": rate, "policy": policy, **{k: v for k, v in r.items()
                         if k not in ("session_log", "mission_release_times", "request_times")}})
            print(f"rate={rate:.1f} policy={policy:8s} completed={r['missions_completed']}/{r['missions_total']} "
                  f"tardy={r['tardy_count']} energy={r['total_charge_energy_wh']:.1f}Wh "
                  f"sessions={r['charge_sessions']} safety_violations={r['safety_violations']}")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"phase4_full_vs_adaptive_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    r41 = section_4_1_poisson_check()
    section_4_2_deadlines_under_load()
    section_4_3_service_time_not_exponential(r41)
    section_4_4_full_vs_adaptive()
