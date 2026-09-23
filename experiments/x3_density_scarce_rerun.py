"""Re-run of X3's density_scarce config only, after the pad-capacity bug
fix (2026-09-23, CLAUDE.md Section 13): `time_to_ready_cost` used to set
`start = t_arr` unconditionally whenever `use_queue_term=False`, ignoring
the chosen pad's actual free time -- verified to let up to 5 drones
"charge" concurrently at a 1-pad station. Fixed to
`start = max(t_arr, free_time_by_pad[best_pad])`, dropping only the W_j
*cost* term (B3's own definition), not pad occupancy. A physical
occupancy backstop was also added at the CHARGING transition itself
(mirrors baseline/jsq's own pads_busy check), plus a hard per-tick
capacity invariant that now raises if any station is ever over capacity.

This re-runs ONLY density_scarce (all 9 policies, same 30 (layout, seed)
pairs as the original X3 run) since that's the one config where B3's
result (0.000 miss rate) was suspect -- every other X3 config already
showed near-zero miss rate for every ablation, so the bug's numerical
impact there is expected to be negligible, but this script could be
pointed at any CONFIGS entry from x3_baselines_vs_ours.py if a broader
re-run is wanted later.

Usage: `python experiments/x3_density_scarce_rerun.py`
"""

import csv
import datetime
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.x3_baselines_vs_ours import (CONFIGS, POLICIES, layout_seed_pairs, run_one)

CONFIG_NAME, N_STATIONS, MISSION_RATE = CONFIGS[0]
assert CONFIG_NAME == "density_scarce"


def main():
    pairs = layout_seed_pairs(n_layouts=5, n_seeds_per_layout=6)
    assert len(pairs) == 30
    total_runs = len(POLICIES) * len(pairs)
    print(f"X3 density_scarce re-run (post pad-capacity fix): {len(POLICIES)} policies x "
          f"{len(pairs)} pairs = {total_runs} runs")
    t0 = time.time()
    all_rows = []
    for policy_name, kwargs in POLICIES:
        for layout_id, seed in pairs:
            r = run_one(kwargs, N_STATIONS, MISSION_RATE, layout_id, seed)
            all_rows.append(dict(
                config=CONFIG_NAME, policy=policy_name, layout_id=layout_id, seed=seed,
                missions_total=r["missions_total"], missions_completed=r["missions_completed"],
                unfinished_at_cap=r["unfinished_at_cap"], miss_rate=r["miss_rate"],
                f12_Z=r["f12_Z"], f12_cmax_term=r["f12_cmax_term"],
                f12_energy_term=r["f12_energy_term"], f12_tardy_term=r["f12_tardy_term"],
                safety_violations=r["safety_violations"], gate_binding_rate=r["gate_binding_rate"],
                mean_on_pad_queue_length=r["mean_on_pad_queue_length"],
                charge_sessions=r["charge_sessions"],
            ))
        print(f"  policy={policy_name} done, elapsed={time.time()-t0:.1f}s", flush=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = ROOT / "results" / f"x3_density_scarce_rerun_{timestamp}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} rows to {out_path}, elapsed={time.time()-t0:.1f}s")

    print("\n=== density_scarce, all 9 policies, post-fix (mean across 30 pairs) ===")
    for policy_name, _ in POLICIES:
        rows = [r for r in all_rows if r["policy"] == policy_name]
        z = np.mean([r["f12_Z"] for r in rows])
        miss = np.mean([r["miss_rate"] for r in rows])
        unfin = np.mean([r["unfinished_at_cap"] for r in rows])
        safety = sum(r["safety_violations"] for r in rows)
        print(f"  {policy_name:28s} Z={z:.4f}  miss_rate={miss:.4f}  unfinished_at_cap={unfin:.2f}  "
              f"safety_violations={safety}")

    # Paired Wilcoxon, ours vs B3, on the corrected data (same pairing as
    # the original X3 pre-registration).
    ours_rows = {(r["layout_id"], r["seed"]): r for r in all_rows if r["policy"] == "ours"}
    b3_rows = {(r["layout_id"], r["seed"]): r for r in all_rows if r["policy"] == "B3_use_queue_term_False"}
    keys = sorted(ours_rows.keys())
    for metric in ("f12_Z", "miss_rate"):
        diffs = [ours_rows[k][metric] - b3_rows[k][metric] for k in keys]
        if any(d != 0 for d in diffs):
            stat, p = wilcoxon(diffs)
        else:
            p = 1.0
        print(f"\nours vs B3, {metric}: mean diff (ours-B3)={np.mean(diffs):.4f}, Wilcoxon p={p:.4g}")


if __name__ == "__main__":
    main()
