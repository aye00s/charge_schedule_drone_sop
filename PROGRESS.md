# Progress checklist — Queue-Aware Charge Scheduling (simulation track)

> Maintained alongside `CLAUDE.md` (which has the full narrative status in
> Section 13) and `HISTORY.md` (pre-remediation Phase 1-7 detail, moved out
> 2026-09-22 to keep CLAUDE.md lean). This file is just the at-a-glance
> checklist — update it whenever a task is completed, a pass gate is met,
> or an item becomes blocked. Keep entries short; details and numbers live
> in CLAUDE.md.

Last updated: 2026-09-22 — **ACTIVE WORK: see `REMEDIATION.md`.** Checkpoints 1-4 done, 80 tests passing. X3 run complete (1350 runs) — **headline finding: `ours` does NOT dominate the primary metrics; queue-awareness (B3 ablation) actively HURTS miss rate under scarce-station contention**, not yet root-caused. See CLAUDE.md Section 13. X4 plan given to the user next. Pre-remediation Phase 1-7 status has moved to `HISTORY.md`; this checklist now tracks REMEDIATION.md's checkpoints only. Checkpoint numbers below match REMEDIATION.md Section 9's own numbered list.

### REMEDIATION.md progress
- [x] Checkpoint 1: Section 7 open decisions answered (energy model, JIT default, objective weights, priority weights)
- [x] Checkpoint 2: E3, E4, E5, E6, E7 — done, see CLAUDE.md Section 13 for full detail. E5/E6 re-verified directly from code (not docs) on 2026-09-22. E6 was checked and found not to reproduce (already correct); the rest were real bugs, fixed and tested.
- [x] Checkpoint 3: E1, E2 fixed; X1 run (minus R4, decided dropped — see below), X2 folded into E2's bias table. **Corrected twice after review** (2026-09-22) — see CLAUDE.md Section 13 for the full, current numbers; summary below.
  - E2: cubic-spline crossover estimator, bias on exact analytic inputs now <0.001 on all 3 grids (was up to 0.0058).
  - E1: R1 t-crossover CIs now contain the true Table-3 crossover at **all 3** (n,m) points (a (10,9)-vs-(4,6) table-transcription bug meant the real miss was (4,6), not (10,9); re-run at horizon=200,000 closed it — the same finite-horizon-bias mechanism as originally found, just at the right config).
  - **R3a corrected (2026-09-22, after user review caught a real interpretation error):** a pooling-bound sanity test at ρ=0.5 confirmed R3a cannot beat concentrated at negligible blocking, as queueing theory requires. A full ρ=0.2-1.6 diagnostic grid then showed **R3a loses to concentrated at every point from ρ=0.2 to 1.1**, converging to statistical noise only in deep overload (ρ=1.2-1.5, <1% difference). The original "None" result was correct (no real crossover in the tested range) — my error was interpreting "None" as "R3a wins throughout" without checking direction. **Smart JSQ routing does not outperform pooling on mean wait; this reverses the earlier "shift of ~0.11-0.13" narrative**, which was built on the pre-E1 L-metric and does not survive the corrected wait-time metric.
  - **R3b corrected (2026-09-22, after user review caught two more real bugs):** the original R3b-vs-concentrated comparison repeated E1's exact per-pad-vs-whole-hub error, then a first fix used the wrong field (`wait`, on-pad-only) instead of `total_delay` (includes travel, per E4c's accounting rule), also mixing rescaled and unrescaled units. Properly fixed and re-run across 5 layouts, with blocking probability and paired per-layout CIs added: **concentrated wins decisively at ρ=0.6/0.8 (blocking negligible for everyone — a genuine queueing result), R3b wins decisively at ρ=1.0/1.2 (driven substantially by blocking-probability divergence — 7.3% vs 3.0% at ρ=1.0)**, consistent on both total delay and total queue across every layout except one at ρ=1.0 (layout 1's paired CI overlaps zero). **Limitation recorded:** this queue-only model's 1/μ=1min is comparable to R3b's travel times (up to ~3min) but far below real CC-CV charge durations (tens of minutes) — no further R3b queue-only runs planned; the travel-vs-charging-time question moves to X4.
  - **Total-queue crossover (n·L_d vs L_c) corrected** (2026-09-22): originally reported 0.750/0.800/0.900 from a bisection bracket that never contained the real root; corrected via a fine scan to **0.9838/0.9889/0.9956** (all three configs), much closer to Table 3's own crossover than Table 2's — now the working explanation for why Tables 2 and 3 disagree (`CLAUDE.md` Section 3.3).
  - R4 (R3a+JIT) dropped from X1 by decision (2026-09-22): non-work-conserving in a random-service-time model, would only measure estimate error, not a real effect. JIT tested only where F7 holds — X3/X4's `ours+JIT` variant.
- [x] Checkpoint 4: F1-F12+F14 + full heuristic as `policy='ours'` in the Phase 4 simulator. **First pass (2026-09-22) reported complete was wrong** — it built a separate parallel engine (`sim/ours_policy.py`) instead of integrating into `sim/mission_sim.py` as REMEDIATION.md Section 3 literally specifies, and never implemented F12. Caught when the user asked to confirm from the code. **Real version, same day**: `run_mission_sim` gained `policy='baseline'|'jsq'|'ours'` (B1/B2=baseline, B4=new jsq routing, B3=ours+use_queue_term=False); F12 objective added with normalized terms, computed for every run; a drain period (`drain_cap_min`) added so F12's makespan/tardiness terms mean something on runs that would otherwise cut off mid-mission; invalid parameter combinations now raise `ValueError`. Exact backward compatibility verified against golden pre-refactor output (bit-for-bit on 3 configs) before merging, and the standalone `run_mission_sim_ours` verified bit-for-bit equivalent before it was deleted. `tests/test_prediction.py` now actually tests "the Phase 4 simulator" per Section 5's wording. New `tests/test_regression.py` re-confirms Phase 1/2 validation and both Phase 3 sanity checks still pass, plus the new exact-reproduction test. See CLAUDE.md Section 13 for the full report, including the deterministic-prediction test output and a labelled smoke run of every policy/ablation.
- [~] Checkpoint 5 (X3, X4, X6 — main result): **X3 done** (1350 runs, 9 policies × 5 configs × 30 layout/seed pairs, 0 safety violations, ~32min). Pre-registered primary analysis (F12 Z + miss rate, ours vs baseline/jsq/B3, paired Wilcoxon+Holm): `ours` loses on Z in 4/5 configs (energy-term driven — the already-known partial-charging penalty, HISTORY.md) and has the *worst* miss rate of the 4 primary policies in `density_scarce` (0.215 vs B3's 0.000) — turning off `use_queue_term`, `use_reservation`, or `use_charge_time_term` each independently fixes it; `use_priority`/`use_partial` do not. Root cause not yet investigated. X4, X6 not started.
- [ ] Checkpoint 6 (X5 — energy re-analysis)
- [ ] Checkpoint 7 (E8, E9; MILP v2; X7)
- [ ] Checkpoint 8 (X8 — weight sensitivity)
- [ ] Final CLAUDE.md / report update (Section 8)

## Phase 1 — Analytical replication ✅ PASS GATE MET
- [x] `L_distributed`, `P0_concentrated`, `P_full_concentrated`, `L_concentrated`, `t_distributed`, `t_concentrated`, `bisect`
- [x] `validate_table2`, `validate_table3`
- [x] Tests (`tests/test_phase1.py`) — 5 passed
- [x] Verified against paper Tables 2/3 — deviation stable at 3.06e-4 / 5.82e-5 (matches paper's own bisection precision)

## Phase 2 — Discrete-event simulator validation ✅ PASS GATE MET
- [x] `simulate_mmnm` event-driven engine (`sim/core.py`)
- [x] Sanity tests — ranges, determinism, light/heavy load
- [x] Bug caught+fixed: L must be queue-only (waiting, excluding in-service), not total-in-system
- [x] Reduced-grid validation — worst error 3.5%
- [x] Full-grid validation (336 rows, all 7×4 n,m pairs) — worst error L_d=2.9%, L_c=6.5%, t_d=3.2%, t_c=6.4%
- [x] Fast regression test embedded in routine `pytest` suite

## Phase 3 — Add the scheduler ⏳ IN PROGRESS
- [x] R1 (FCFS, fixed-split routing) — `sim/scheduler.py`
- [x] R2 (priority=least-slack-first, fixed-split routing)
- [x] R3a (priority, JSQ routing)
- [x] R3b (priority, JSQ + travel geometry) — geometry decision settled by proceeding (2000m×2000m area, fixed random station layout, 15m/s speed)
- [x] Mandatory sanity check 1: slack-zero reduction — passing
- [x] Mandatory sanity check 2: conservation check (H1) — passing
- [x] Full regime comparison (15 seeds, R1-R3b, 480 rows) — H3 directionally supported (R3a shifts crossover left); R3b shows a mechanistically-explained three-way split (worse than R1 at low ρ due to travel-dominated routing on a lopsided random station layout, best of all four at high ρ) — needs a second layout/seed to confirm it's not geometry-specific; blocking/wait trade-off and H2 counter-example also documented in CLAUDE.md Section 8
- [x] Phase-6-grade statistics on the headline finding (≥30 seeds, CRN, bootstrap CI on ρ\* shift) — **done**: R1 ρ\*=0.7505 [0.7500,0.7509] (matches Phase 1 analytic 0.75049 almost exactly); R3a ρ\*=0.6232 [0.6227,0.6236] — non-overlapping CIs, H3 crossover shift now statistically confirmed, not just directional. Paired Wilcoxon p=1.86e-09 at every ρ.
- [x] Extended to grid extremes (n=4,m=6 and n=10,m=9), 30 seeds each — **crossover-shift finding generalizes**: consistent shift magnitude (~0.11-0.13) across all 3 points tested (grid corners + middle), not a fluke. One honest caveat: coarser 5-point rho grids at the extremes gave R1 estimates just outside the analytic CI (vs dead-center at n=5,m=7's 6-point grid) — plausibly interpolation resolution, not a real discrepancy.
- [ ] Full 28-point (n,m) grid — 3 representative points done; the complete grid confirmed infeasible in one sitting (~58min/point, ~27h extrapolated). R3b not yet brought to this rigor.

## Phase 4 — Mission layer ✅ CORE WORK DONE (4.1-4.4)
- [x] `sim/energy.py` — flight energy model (κ corrected from CLAUDE.md's example to a physically consistent value) + 3-band CC-CV curve
- [x] `sim/models.py` — UAV/Station/Mission dataclasses
- [x] `sim/mission_sim.py` — discrete-time mission engine; real bug found+fixed (reachability gate didn't check return-to-station feasibility)
- [x] 4.1 Energy-driven charge requests — emergent stream CV=0.883 (~Poisson-ish, not exact)
- [x] 4.2 Deadlines / tardiness / miss rate — sharp overload transition at rate=1.5/min (47.3% tardy)
- [x] 4.3 CC-CV service time (M/G/c) — confirmed non-exponential (CV=0.031)
- [x] 4.4 Partial charging — bug found+fixed (target could undershoot recharge trigger, causing an infinite zero-duration charge loop); after fix, adaptive uses *more* energy than full-charge at every load tested (+7-11% mean, confirmed stable across 5 seeds × 2 load levels, no exceptions), contradicting the naive hypothesis (reported as-is)
- [x] Least-slack-first ordering layered on top of charge-target policy — **done**: `order='priority'` in `run_mission_sim`. First look (1 seed, rate=1.5) suggested a big win; a proper 20-seed paired test found it's actually **not significant** (p=0.22, mixed per-seed direction) at the overload boundary, and also not significant at deep overload (p=0.18). Honest null result, not the anecdote it first looked like.
- [x] Phase-6-grade statistics (≥30 seeds, CIs, paired Wilcoxon) — done (`experiments/phase4_stats.py`): +7.90% [6.90,8.99] at rate=0.6, +10.64% [10.11,11.18] at rate=1.2, Wilcoxon p=1.86e-09 both (maximum possible significance at n=30, every seed agreed)

## Phase 5 — MILP validation ✅ CORE WORK DONE
- [x] `sim/milp.py` — PuLP+CBC MILP, v1 scope: single constant charging rate per station (base linear version, kept for the validated hand-checkable instance); C9/C10 now also implemented in a separate function (see below)
- [x] Hand-checkable 4-drone instance — MILP objective=8.0, matches manual calculation exactly
- [x] Real bug found+fixed: SoC recurrence used `==` instead of `<=`, causing false "Infeasible" whenever a charging decision would physically overshoot 100% (caught by cross-checking against a heuristic solution that was independently verified feasible)
- [x] Comparable greedy least-slack-first heuristic built for genuine optimality-gap comparison (`solve_charge_schedule_heuristic`)
- [x] Optimality-gap sweep (8 instances, 4-12 drones, 1-3 stations) — 7/8 feasible instances all show exactly **0% gap**; 8th (tightest, 1 pad) correctly Infeasible on both solvers.
- [x] Robustness check (15 more random instances, 3 configs × 5 seeds) — **all 15/15 also 0% gap**. Combined total: **22/22 feasible instances at 0% gap, out of 23 tested** (1 correctly Infeasible on both solvers) — corrected here from an earlier "23/23" miscount. Likely explained by this v1 scope's uniform pad-slot cost (no tariff/travel heterogeneity yet) making least-slack-first near-optimal by construction — not a claim that the heuristic is generally optimal once costs become heterogeneous.
- [x] Open decision: does W_j enter the MILP? — settled by proceeding with the recommended default (no, keep implicit)
- [x] Full CC-CV piecewise charging (C9) and charging continuity (C10) — **done** (`solve_charge_schedule_milp_ccv`). The originally-documented C9 formulation was wrong (caught before implementing); corrected version uses proper band-selection indicators. Two more real bugs found+fixed while building it (free-SoC-jump when not charging; spurious SoC decrease with no discharge model) — both caught via sanity tests before trusting output. 4 new tests, 10/10 passing in `test_phase5_milp.py`.
- [ ] Re-run optimality gap using the CC-CV MILP (only measured against v1's flat-rate version so far) — natural way to find a nonzero gap

## Phase 6 — Scale and statistics ✅ DONE except capacity-m axis
- [x] 4→60 drone sweep (5,10,20,40,60), ≥30 seeds, paired Wilcoxon tests, runtime scaling — **done**, headline finding: adaptive-vs-full energy comparison **reverses sign** between n=10 and n=20 (−23%/−21% at small fleets → +5%/+9%/+13% at larger fleets), every point p=1.86e-09. Contradicts H5's "largest benefit at high load" — benefit found at small scale instead. Runtime: ~11μs/decision (n=5) → ~100μs/decision (n=60), mildly super-linear (flagged, not fixed).
- [x] Station density (scarce/balanced/abundant) — **done**: scarce amplifies the adaptive-charging penalty ~4x (+18.92% vs +4.91-5.28% for balanced/abundant), all p=1.86e-09.
- [x] Mission-load axis (independent of fleet size) — **done**: light load shows no significant difference (p=0.349); saturated load blows the penalty up to +41.76% (p=1.86e-09). Combined with density and fleet-size axes, gives a coherent "penalty grows with system contention along every axis" story.
- [x] Tariff (flat/time-of-use) — **done**, `sim/tariff.py` + per-tick cost tracking in `mission_sim.py`. Result (ToU ~18-19% cheaper) flagged as mostly a horizon artifact (1000min run never reaches the 17:00-21:00 peak window), not a validated finding. Neither policy is tariff-aware yet.
- [ ] Capacity-m axis at Phase 6 scale — covered at Phase 2 scale only, not re-run here

## Phase 7 — Figures and writing ⏳ STARTED
- [x] 9 figures generated from saved CSVs (`experiments/make_figures.py` → `figures/`)
- [x] 15-page results report PDF compiled (`experiments/make_report.py` → `Phase1-6_Results_Report.pdf`), covering all of Phases 1-6 plus a 7-bug summary and an explicit "what's missing" section
- [ ] Full paper write-up (methods narrative, baseline comparison against threshold/nearest-greedy policies) — not started, the PDF above is a results report, not the paper

## Hardware track ⬜ NOT STARTED
Out of scope for now — user has directed focus to the simulation track only (see CLAUDE.md Section 14 note).

## Open decisions still outstanding
- Exact form of the flight power model (Section 4.3, two candidates — the flat-rate kappa is in use, the fuller P(v,m) model is not built).

Settled: slack distribution (Exponential, mean=1/μ), Phase 3 priority weights (pure least-slack-first, w1=1/w2=0), R3b geometry (2000m×2000m area, fixed station layout, 15m/s), does W_j enter the MILP (no, keep implicit), formal statements of C9 and C10 (both implemented in `solve_charge_schedule_milp_ccv`) — see CLAUDE.md Section 13.
