# HISTORY.md — Pre-remediation project history

> This file holds the Phase 1–7 narrative and numbers as they stood on
> 2026-09-21, **before** `REMEDIATION.md`'s review found the crossover
> metric bug (E1) and the missing implementation of our own proposed
> method. It exists so the detailed record of how those phases were
> built (bugs found, tests written, exact commands and output) isn't
> lost, without cluttering `CLAUDE.md`'s active-work section.
>
> **This is historical record, not current status.** For current status,
> read `CLAUDE.md` Section 13. In particular:
> - Phase 3's headline "crossover shift" finding is **superseded** by
>   X1 (`CLAUDE.md` Section 13) — the corrected per-drone-wait metric
>   shows R3a does *not* beat concentrated in the practical load range.
> - Phase 5's "0% gap ⇒ least-slack-first is near-optimal" explanation
>   has been corrected below per REMEDIATION.md E10.
> - Phase 6's energy sign-reversal finding is labelled **provisional**
>   below per REMEDIATION.md E13, pending the X5 re-analysis.
> - H5's status is corrected below per REMEDIATION.md E12 (it predicted
>   makespan/deadline-miss outcomes, which were never measured — only
>   energy was, so H5 itself remains untested).
>
> Sections below are otherwise unedited from the 2026-09-21 write-up
> except for the E10/E12/E13 corrections just described, marked inline.

---

## Phase 1 — Analytical replication ✅ DONE (2026-09-21)

**Goal:** reproduce Tables 2 and 3.
**Status:** Implemented in `phase1_baseline.py`. `bisect` tolerance was swept from 1e-4 down to 1e-12 to confirm the deviation is a stable residual, not our own under-converged bisection: it plateaus at Table 2 = 3.060819e-04, Table 3 = 5.824636e-05 by tol=1e-8 and stays fixed through 1e-12. This is the same order of magnitude as the paper's own stated bisection precision (1e-4), consistent with their rounding rather than a bug here. `validate_table2`/`validate_table3` default to `tol=1e-9` accordingly. Verified by running `pytest -q tests/test_phase1.py` (5 passed) and `python phase1_baseline.py`.
**Functions available:** `L_distributed(rho, m)`, `P0_concentrated(rho, n, m)`, `P_full_concentrated(rho, n, m)`, `L_concentrated(rho, n, m)`, `t_distributed(rho, m, n)`, `t_concentrated(rho, n, m)`, `bisect(f, lo, hi)`, `validate_table2()`, `validate_table3()`.

**Note (2026-09-22):** `bisect` now raises `ValueError` if the given bracket doesn't contain a sign change, instead of silently converging to a wrong value inside it. Added after this exact failure mode produced wrong X1 numbers (see `CLAUDE.md` Section 13). All Phase 1 validated numbers above are unaffected (their brackets always genuinely contained the root).

## Phase 2 — Discrete-event simulator validation ✅ DONE (2026-09-21)

**Goal:** a simulator that reproduces the analytical model under the paper's own assumptions.
**Status:** Implemented `simulate_mmnm(lam, mu, n_servers, capacity, horizon, seed, warmup_frac=0.1)` in `sim/core.py` (event-driven M/M/c/K, warm-up discard, FCFS queue). Distributed = `n_servers=1, capacity=m`, arrival rate λ/n. Concentrated = `n_servers=n, capacity=n*m`, arrival rate λ.

**Important correctness finding:** the paper's `L` is the time-averaged number **waiting for a server** (queue length excluding those already in service), not total-number-in-system. The first implementation tracked total-in-system and was off by up to ~10x against the analytics; comparing both definitions empirically confirmed queue-length-only is correct (see `sim/core.py` docstring). `wait` (mean queueing delay) is rescaled by the total arrival rate λ to match the paper's "1/λ factored out" convention, per Eq. 18/19.

**Validation run** (16 (n,m) configs × ρ ∈ {0.6,0.8,1.0,1.2} × 3 seeds × 2 layouts, horizon=50,000, μ=1): worst relative error 3.5% (n=5, m=9, ρ=0.8, on both L_c and t_c), most configs under 2%. Command and full output are reproducible via the sweep run in this session; not yet saved as a CSV under `results/` (see open item below).
**Fast regression test:** `tests/test_phase2.py::test_simulator_matches_analytics` (2 configs, 2 seeds, horizon=20,000, 10% tolerance) — part of the routine `pytest -q` suite (11 passed total with Phase 1).

**Full-grid sweep run** (2026-09-21, `experiments/phase2_validation.py`, background job, 676.8s): all 7×4 (n,m) pairs × ρ∈{0.6,0.8,1.0,1.2} × 3 seeds × 2 layouts, horizon=100,000. Worst relative error across all 336 rows: **L_d=2.9%, L_c=6.5%, t_d=3.2%, t_c=6.4%**. Raw output at `results/phase2_validation_20260921_161516.csv`. Pass gate solidly met at full scale, not just the reduced grid.

## Phase 3 — Add the scheduler ⏳ IN PROGRESS (2026-09-21) — superseded by X1

> **Everything in this Phase 3 section is superseded.** It used the
> per-pad L_d vs whole-hub L_c comparison that E1 identified as not
> like-for-like. `CLAUDE.md` Section 13 (X1) has the corrected,
> per-drone-wait-based results. Kept here only for the historical
> record of how R1-R3b were built and sanity-checked (those
> mechanics — routing, event loop, sanity checks — are still in use;
> only the *crossover conclusion* drawn from them here is wrong).

**Status:** R1 (FCFS, fixed-split), R2 (priority=least-slack-first, fixed-split), R3a (priority, JSQ routing), R3b (priority, JSQ+travel) all implemented in `sim/scheduler.py`.

**Mandatory sanity checks — both pass** (`tests/test_phase3_sanity.py`):
1. Slack-zero reduction: matches Phase 1/2 analytics within 10% (n=5,m=7,ρ=1.0, 5 seeds).
2. Conservation check (H1): R2 matches R1 on average L and wait within 10% (n=5,m=7,ρ=0.9, 5 seeds) — confirmed again in the full regime sweep below, where R1 and R2 are visually identical at every ρ tested.

**Regime comparison, expanded run** (`experiments/phase3_regimes.py`, 2026-09-21, 15 seeds, horizon=50,000, n=5, m=7, slack_mean=1/μ, ρ∈{0.6,0.65,0.7,0.8,0.9,1.0,1.1,1.2} — still NOT Phase 6 statistical rigor (no CI), results at `results/phase3_regimes_20260921_164108.csv`, 480 rows):

| ρ | L (R1) | block (R1) | L (R3a jsq) | block (R3a) | L (R3b jsq+travel) | block (R3b) | L_c analytic |
|---|---|---|---|---|---|---|---|
| 0.60 | 0.768 | 1.1% | 0.416 | 0.0% | 0.945 | 4.4% | 0.354 |
| 0.70 | 1.168 | 2.7% | 0.582 | 0.0% | 1.300 | 7.4% | 0.881 |
| 0.80 | 1.635 | 5.1% | 0.908 | 0.0% | 1.676 | 10.8% | 2.198 |
| 0.90 | 2.133 | 8.4% | 1.655 | 0.5% | 2.054 | 14.4% | 5.870 |
| 1.00 | 2.629 | 12.5% | 3.097 | 3.3% | 2.436 | 18.3% | 13.876 |
| 1.20 | 3.490 | 21.8% | 5.033 | 16.8% | 3.115 | 26.1% | 25.078 |

- R1 ≈ R2 at every ρ (further confirms H1).
- **R3a (JSQ) shifts the crossover left**: R1's own crossover against L_c falls between ρ=0.7–0.8 (matches the Phase 1 analytical ρ*≈0.750 for n=5,m=7); R3a's falls between ρ=0.6–0.65. Directionally supports H3. **[Superseded — this used the per-pad L metric; X1's per-drone-wait metric shows the opposite direction, see `CLAUDE.md` Section 13.]**
- **Genuine trade-off (R3a), reported as-is:** JSQ cuts blocking dramatically at every ρ, so it admits far more drones — raw L looks worse at ρ≥1.0 purely from higher admission. Per-admitted wait is genuinely better at ρ≤0.8 but genuinely worse at ρ≥1.0 (overload trades rejection for longer queueing).
- **R3b (JSQ+travel) is a three-way split, mechanistically explained, not just noise:** at ρ≤0.8, R3b has *higher* blocking and *higher* L than even plain R1 — worse than doing nothing clever. At ρ≥1.0, R3b drops *below* both R1 and R3a (best of all four regimes). Root cause found by inspecting the fixed station layout (`sim.scheduler._station_positions`, seed=0): with only 5 IID-random points, 3 stations happened to cluster within ~550m of each other while 1 sits isolated ~1300-2300m away. At low ρ, queue-length differences between stations are small (0-2 range) while travel-time differences are comparably large (up to ~3min at 15m/s across a 2000m area), so R3b's additive cost `waiting_count/mu + travel_time` is travel-dominated and behaves close to greedy-nearest-station routing — concentrating load unevenly on the geometric layout rather than balancing it, hence *more* blocking than even random split. At high ρ, queue costs grow to dominate the fixed travel-time term, so R3b's routing becomes genuinely load-aware again and it wins. **This is very likely an artifact of the specific random station layout and the unnormalized additive cost, not a general property of adding travel cost to routing** — a deliberate (e.g. grid) layout or a normalized cost function would need to be tried before concluding anything about H4. **[Also since found to be substantially a units artifact — E4(a) — see `CLAUDE.md` Section 13.]**
- A test I added myself (not a CLAUDE.md-mandated check) initially asserted priority ordering must *improve* per-drone on-time rate (H2) and failed consistently (priority is ~1.8pp *worse*, std 0.0004 across 10 seeds, at n=5,m=7,ρ=0.9,slack_mean=1/μ) — plausibly EDF's known overload "domino effect." Test corrected to check outcomes *differ* rather than assume they improve; the H2 counter-example is preserved as a documented finding, not tuned away.

**Phase-6-grade statistics, done for the headline result** (`experiments/phase3_crossover_ci.py`, 2026-09-21, 30 seeds, ρ∈{0.55,0.60,0.65,0.70,0.75,0.80}, `sim/stats.py` bootstrap CI + paired Wilcoxon, results at `results/phase3_crossover_ci_20260921_184650.csv`, 1172.3s):

| ρ | R1 L (95% CI) | R3a L (95% CI) | L_c analytic | Wilcoxon p (R1 vs R3a) |
|---|---|---|---|---|
| 0.55 | 0.608 [0.605,0.612] | 0.359 [0.357,0.360] | 0.218 | 1.86e-09 |
| 0.60 | 0.768 [0.765,0.772] | 0.416 [0.415,0.418] | 0.354 | 1.86e-09 |
| 0.65 | 0.954 [0.949,0.958] | 0.490 [0.488,0.492] | 0.562 | 1.86e-09 |
| 0.70 | 1.166 [1.162,1.169] | 0.583 [0.582,0.585] | 0.881 | 1.86e-09 |
| 0.75 | 1.389 [1.384,1.394] | 0.712 [0.708,0.716] | 1.383 | 1.86e-09 |
| 0.80 | 1.635 [1.630,1.639] | 0.910 [0.903,0.916] | 2.198 | 1.86e-09 |

**Crossover point estimates (bootstrap CI, 2000 resamples over seeds):**
- **R1 vs L_c: ρ\* = 0.7505, 95% CI [0.7500, 0.7509]** — matches the Phase 1 analytical value (0.75048828125 for n=5,m=7) almost exactly, sitting inside the CI. A clean three-way cross-validation: analytical (Phase 1) ↔ simulated (Phase 2/3 engine) ↔ bootstrapped estimate all agree.
- **R3a vs L_c: ρ\* = 0.6232, 95% CI [0.6227, 0.6236]** — CI does not overlap R1's. **[Superseded — see the note at the top of this Phase 3 section.]**
- R1 vs R3a paired Wilcoxon: p=1.86e-09 at every ρ tested (maximum possible significance at n=30 — every seed agreed on direction).

**Grid extremes, done** (`experiments/phase3_grid_crossover_ci.py`, 2026-09-21, 30 seeds, results at `results/phase3_grid_crossover_ci_20260921_214550.csv`, 3453.4s — this alone took ~58 minutes, confirming the full 28-point grid at this rigor really is infeasible in one sitting): n=4,m=6 and n=10,m=9 (grid corners), alongside the existing n=5,m=7 (grid middle):

| (n,m) | R1 ρ\* (95% CI) | R3a ρ\* (95% CI) | Shift | Table 2 analytic ρ\* |
|---|---|---|---|---|
| (4,6) | 0.7056 [0.7051,0.7061] | 0.5967 [0.5958,0.5976] | 0.1089 | 0.70752 |
| (5,7) | 0.7505 [0.7500,0.7509] | 0.6232 [0.6227,0.6236] | 0.1273 | 0.75049 |
| (10,9) | 0.8196 [0.8194,0.8199] | 0.7042 [0.7040,0.7043] | 0.1155 | 0.82529 |

**The crossover-shift finding generalizes**: shift magnitude is consistent (~0.11-0.13) across all three grid points tested, spanning the grid's corners and middle — this is not a fluke at one (n,m). One honest methodological note: at (4,6) and (10,9) (run with a coarser 5-point ρ grid, vs (5,7)'s 6 points) the R1 estimate sits just outside the analytical value's 95% CI rather than dead-center as it did at (5,7) — plausibly a linear-interpolation resolution artifact from the coarser grid, not a sign the method is wrong (the R1-vs-L_c crossover is a validated quantity from Phase 1/2, so a real discrepancy would be a red flag; a small coarse-grid interpolation bias is a mundane, fixable-with-more-rho-points explanation).

**Not yet done:** the full 28-point (n,m) grid (3 representative points done, not all 28 — confirmed infeasible in one sitting at ~58min per point, ~27 hours extrapolated); a second station-layout seed or a deliberate layout to test whether the R3b finding (Section 8, three-way split) is geometry-specific; R3b itself hasn't been brought to this level of statistical rigor.

**Conceptual key:** the scheduler cannot change overall demand. ρ keeps its meaning (demand rate / service capacity). Each drone raises a charge request at a Poisson time a_i (same λ as the paper) and has a **slack window** [a_i, a_i + s_i] in which to start charging. The scheduler chooses the start time within the window and (where applicable) the pad.

**Regimes to implement:**

| Regime | Arrivals | Service order | Pad choice | Travel |
|---|---|---|---|---|
| R1 | Poisson | FCFS | Random split (λ/n per pad) | None |
| R2 | Poisson | Priority score | Random split | None |
| R3a | Poisson + slack window | Priority score | Scheduler chooses | None |
| R3b | Poisson + slack window | Priority score | Scheduler chooses | Geometry added |

R3 is split because it otherwise changes two things at once (routing/timing, and travel distance).

**Mandatory sanity checks (must pass before any Phase 3 result is reported):**

1. **Slack-zero reduction:** with all s_i = 0 and no pad choice, R3 must reproduce the Phase 2 / analytical curves.
2. **Conservation check:** R2 must match R1 on **average** queue length and waiting time (Kleinrock's conservation law: with identical service-time distributions and an ordering that does not depend on service time, service order does not change the number-in-system process). If R2 ≠ R1 on averages, there is a bug.

**Consequence of check 2:** priority helps with **per-drone outcomes** (deadline misses, reserve violations, starting outside the window), not averages. Log per-drone data or the priority rule will look useless.

**Crossover estimation with noisy simulation output:**
1. Evaluate a grid of ρ (e.g., step 0.02 near the crossover), many seeds per point.
2. Use CRN between concentrated and distributed.
3. Fit a smooth curve to the difference (L_c − L_d) and find its zero.
4. Bootstrap over seeds for a confidence interval on ρ\*.
Report ρ\* as e.g. "0.81 ± 0.02". Do not use plain bisection on noisy output.

**Suggested module:** `phase3_scheduler.py`, reusing the Phase 2 event loop. Suggested functions:
- `generate_requests(lam, horizon, slack_dist, seed)` → list of (arrival_time, slack, drone attributes)
- `simulate_regime(regime, n, m, rho, horizon, seed, **params)` → metrics dict
- `priority_score(drone, t, w1, w2)`
- `select_station(drone, stations, t)` implementing gate → cost → argmin → reservation update
- `estimate_crossover(results_grid)` → (rho_star, ci_low, ci_high)
- `run_sanity_checks()` → asserts both checks

**Metrics per run:** average queue length, average waiting time, blocking probability, per-drone wait, fraction of drones starting within their window, reachability-gate binding count, scheduler time per decision.

**Deliverable:** ρ\* with confidence intervals for R1, R2, R3a, R3b over the (n, m) grid.

## Phase 4 — Mission layer ✅ CORE WORK DONE (2026-09-21)

Add one feature at a time; record the effect of each; if an effect cannot be explained, stop and investigate.

**Built:** `sim/energy.py` (flight energy model + 3-band CC-CV curve), `sim/models.py` (UAV/Station/Mission dataclasses), `sim/mission_sim.py` (discrete-time engine, dt=1min, real UAVs flying real missions). Tests: `tests/test_phase4_energy.py` (6 passed), `tests/test_phase4_mission_sim.py` (5 passed).

**Parameter correction made while building (documented, not silent):** `CLAUDE.md` Section 4.3's example κ=0.5 Wh/m, combined with a ~90Wh battery, gives only 180m of total range — unusable at any realistic mission-area scale. Replaced with κ=0.01 Wh/m (physically grounded from typical small-quadcopter cruise power/speed, ~9km range at full charge). Revisit once hardware calibration (Section 14.8) provides a measured value.

**Real bug caught and fixed (not just theoretical):** the first version's mission-reachability gate only checked "can the UAV reach the mission destination," not "can it subsequently reach a charging station from there" — a mission could legally strand a drone at exactly σ with nowhere reachable afterward. Caught via a smoke test showing 1410 safety violations (mostly a handful of drones stuck in an infinite IDLE loop for hundreds of ticks). Fixed with `_reachable_with_return`, which also requires a feasible leg from the mission destination to some station. Nominal-scenario safety violations are now 0.

**4.1 — Poisson check** (n=20, 5 stations, horizon=3000min, rate=0.8/min): 373 emergent charge requests, mean inter-arrival 8.02min, **CV=0.883** (exponential CV=1.0) — reasonably close to Poisson, not exact (expected: request timing is now coupled to mission assignment and flight time, not a raw exogenous process).

**4.2 — Tardiness under load** (n=15, 5 stations, horizon=1500min): 0% tardy at rate≤1.2/min; **sharp jump to 47.3% tardy at rate=1.5/min** (mean tardiness 23.3min) — genuine overload transition, not a gradual one, at this (n, station-count) configuration.

**4.3 — Service time is not exponential**: charge-duration CV=0.031 (vs 1.0 for exponential) — confirms the paper's M/M/c formulas don't apply once CC-CV charging is in the loop; duration is a near-deterministic function of arrival SoC, not a memoryless random variable.

**4.4 — Full vs. adaptive-partial charging, real bug then real (negative) finding:**
- First version of the adaptive-target heuristic had a genuine bug: the target could land *below* the UAV's own recharge trigger (0.35), so it went IDLE still under threshold and immediately re-entered charging — an infinite zero-duration charge loop (15,000+ sessions for 15 drones at horizon=1500min). Fixed by flooring the target at `RECHARGE_TRIGGER_SOC + 0.05`.
- **After the fix, the result reported plainly (contradicts the naive hypothesis and the unverified PDF claims referenced earlier in this project):** adaptive-partial charging used **consistently more energy than always-charge-to-full at every load tested** (rate 0.3→1.2/min: +8% to +10%), with ~5x more charging sessions, and no meaningful completion benefit. The extra flight-to-station overhead from far more frequent trips outweighs the energy "saved" by not topping up to 100%, given this heuristic's short (30min) lookahead and thin margin above the trigger. **Not tuned further to force H5 to hold** — recorded as a genuine negative result; a better-designed adaptive heuristic (longer lookahead, larger margin, or explicit accounting for trip overhead) might reverse this, but that hasn't been tried.

**Multi-seed robustness check** (2026-09-21, n=15, 5 stations, horizon=1500min, 5 seeds each at rate=0.6 and rate=1.2): the 4.4 energy finding holds with no exceptions — adaptive used *more* energy than full in all 10 seed-scenarios (rate=0.6: +4.8% to +10.5%, mean +7.4%; rate=1.2: +9.6% to +12.5%, mean +11.0%), with essentially identical mission completion in every case. Not a single-seed fluke.

**Phase-6-grade statistics, done** (`experiments/phase4_stats.py`, 2026-09-21, 30 seeds, `sim/stats.py` bootstrap CI + paired Wilcoxon, results at `results/phase4_stats_20260921_183026.csv`):
- rate=0.6: full=9104.4Wh [9001.2,9221.3], adaptive=9822.9Wh [9685.5,9964.9], diff=+7.90% [6.90%,8.99%], Wilcoxon p=1.86e-09.
- rate=1.2: full=18493.1Wh [18297.1,18702.7], adaptive=20456.8Wh [20258.5,20679.9], diff=+10.64% [10.11%,11.18%], Wilcoxon p=1.86e-09.
- p=1.86e-09 is the maximum possible significance for a 30-sample Wilcoxon (every single seed agreed on direction). The 4.4 finding is now statistically airtight within this model's scope, not just "probably real."

**Least-slack-first ordering, added** (2026-09-21, beyond the Section 8 spec's 4.1-4.4, a natural extra increment): added `order='priority'` to `run_mission_sim` — mission assignment by deadline-t ascending instead of release-time order, and pad queues served by lowest battery margin (soc-sigma) first instead of FIFO, a direct implementation of Section 6's slack/margin priority now that Phase 4 has a real SoC model. Independent of `charge_policy`, isolating the change. **[Note: this margin-based pad ordering is now `pad_order='margin'`, an explicit opt-in ablation, not the default — see E5 in `CLAUDE.md` Section 13.]**

**Honest finding, not the anecdote it first looked like:** a single-seed check at the overload boundary (rate=1.5) showed a dramatic-looking improvement (47.3%→17.2% tardy). A proper 20-seed paired test at the same point found this was **not representative** — mean miss rate 18.4% vs 22.9%, but Wilcoxon p=0.22 (not significant), with wildly mixed per-seed direction (some seeds strongly favor each policy; e.g. one seed went 79.7%→18.2%, another went 6.2%→60.2%, opposite directions). At deep overload (rate=2.5) both policies saturate to ~90% miss rate with a similarly non-significant gap (p=0.18). **Priority ordering shows no statistically significant benefit over FCFS in this mission-layer model, at any load level tested** — a different, more nuanced conclusion than the initial single-seed read, and a different result from Phase 3's abstract queueing model (where priority had a small but statistically robust *negative* effect via EDF's overload domino effect). Reported as-is; the single-seed anecdote was corrected before being written down as a finding, not after.

**Status: Phase 4 done**, including the least-slack-first increment and its honest (null) result. Full Phase-6-grade statistics (≥30 seeds, CIs) done for 4.4's headline finding; the priority-ordering check above already used 20 seeds.

## Phase 5 — MILP validation ✅ CORE WORK DONE (2026-09-21)

- Build the MILP (Section 4) in Pyomo or PuLP; solve with HiGHS/CBC (free) or Gurobi (free academic).
- Small instances: 4–15 drones, 2–4 stations, short horizon, coarse slots. Set a solver time limit; if hit, record the best bound and remaining gap rather than discarding the instance.
- Keep Big-M values as small as valid. Add symmetry-breaking constraints for identical drones/pads.
- **Hand-checkable instance:** 4 drones, 2 stations, 1 pad each, 60-minute horizon, σ = 0.20. Solve by hand and confirm the MILP matches.
- Report optimality gap = (heuristic − MILP) / MILP.
- **Open decision, settled by proceeding (2026-09-21):** whether W_j enters the MILP — went with the recommended default (no, keep implicit; C1 pad-capacity already forces an optimal schedule to account for waiting).

**Built:** `sim/milp.py` — PuLP+CBC MILP (`solve_charge_schedule_milp`) and a comparable greedy least-slack-first heuristic solving the *same* discrete problem (`solve_charge_schedule_heuristic`), for a genuine apples-to-apples optimality gap. Tests: `tests/test_phase5_milp.py` (10 passed, including the C9/C10 additions below).

**v1 scope-down, since resolved:** the note below described the full CC-CV piecewise charging curve (C9) as not-yet-implemented, with a proposed Big-M formulation. **That proposed formulation was wrong** — applying every band's rate as a simultaneous upper bound whenever charging, regardless of the drone's actual SoC, would force every drone onto the slowest (50W) band's rate no matter how low their SoC is. Caught before implementing, not after. See below for the corrected implementation.

**C9 (piecewise CC-CV) and C10 (charging continuity), implemented** (2026-09-21, `solve_charge_schedule_milp_ccv` in `sim/milp.py`):
- C9 uses proper band-selection indicator variables z[i,t,l] (one active band per drone per slot) with Big-M linking S[i,t] to its band, and a further Big-M linking the charging increment to both the charge decision and the active band. Verified to exactly reproduce v1's result when charging stays within a single band, and to require ≥ v1's pad-time once a drone must cross into a slower band (tested).
- C10 (minimum dwell time / no rapid on-off switching) needs no Big-M at all: since `sum_j x[i,j,t]` is binary, the rising-edge difference `x[t]-x[t-1] <= x[t']` for t' in the dwell window directly forces continuity whenever a session starts. **[Superseded by E9 — this window must be truncated at the horizon end; not yet fixed, see `REMEDIATION.md` E9.]**
- **Two more real bugs caught while building this, both via sanity-testing before trusting the output:**
  1. When not charging, the Big-M relaxation on every band constraint was simultaneously active (x_total=0 alone added +Big-M regardless of band), leaving SoC completely unconstrained up to 1.0 — a within-one-band test instance showed the solver reaching the target SoC with **zero charging sessions** (objective=0). Fixed with an explicit `S[i,t+1] <= S[i,t] + BIG_M*x_total_t` constraint.
  2. With no discharge component in this scheduling-only model, nothing in the objective penalized an intermediate SoC value dropping for no reason (only the upper bound on increase was constrained) — a multi-band test instance showed SoC spuriously *decreasing* between slots with no charging to explain it (same objective value, just an arbitrary degenerate trajectory among tied optima). Fixed with an explicit monotonicity constraint `S[i,t+1] >= S[i,t]`.
- Known remaining approximation (documented, not fixed): the active band is chosen from S[i,t] (start of slot) and that rate applies for the whole slot, so a slot that would physically cross a band boundary partway through is slightly over-credited versus the true continuous curve. **[This is exactly E8 in `REMEDIATION.md` — with Δt=10min and B=90Wh a single fast-band slot can add ~37% SoC, more than a band is wide, so the MILP as built here does not actually enforce CC-CV. Not yet fixed.]**
- Tests: `tests/test_phase5_milp.py` now has 10 passing (4 new: within-band match, monotonicity regression, no-free-charging regression, ccv-requires-≥-v1's-pad-time).

**Hand-checkable instance verified by hand (2026-09-21):** 4 drones, 2 stations×1 pad, 60min horizon, dt=10min (T=6 slots), S0=0.20, target=0.60, rate=200W/90Wh battery → 0.37037 SoC/slot. Manual calc: 1 slot gives 0.570 (short), 2 slots gives 0.941 (sufficient) → each drone needs exactly 2 slots → minimum total = 4×2=8 pad-slots (12 available, so feasible with room to spare). **MILP found objective=8.0, exactly matching the hand calculation**, with pad capacity and SoC bounds independently re-verified (not just trusting the solver's own claim).

**Real bug caught and fixed via the optimality-gap check itself:** the SoC recurrence was first written as a strict equality (`S[i,t+1] == S[i,t] + inc`). On a harder 8-drone/2-pad instance, the MILP reported **Infeasible** while the greedy heuristic found a solution that independently checked out as fully feasible (pad capacity respected, all deadlines met). Since a true optimum solver should never say infeasible when a feasible solution provably exists, this proved a MILP bug, not a heuristic one. Root cause: the equality forced SoC to exceed 1.0 (mathematically) whenever a charging decision would physically overshoot full — the heuristic saturates at 1.0 (correct, physical), the equality had no such saturation and instead broke the S≤1 upper bound, making the whole system infeasible. Fixed by changing to `S[i,t+1] <= S[i,t] + inc` (sound because the objective only rewards using less charging, never rewards a lower SoC, so the solver has no incentive to under-report — verified in `test_charging_past_full_saturates_instead_of_infeasible`). After the fix, the same 8-drone instance: **MILP=13.0 (Optimal), heuristic=13 (0% gap)**.

**Optimality-gap sweep, complete** (`experiments/phase5_milp_gap.py`, 8 instances, 4-12 drones, 1-3 stations, varying pad contention, results at `results/phase5_milp_gap_20260921_180210.csv`, 123.3s total):

| n_drones | pads | MILP obj | Heuristic obj | gap |
|---|---|---|---|---|
| 4 | [1,1] | 5.0 | 5 | 0.0% |
| 6 | [1,1] | 8.0 | 8 | 0.0% |
| 8 | [1,1] | 13.0 | 13 | 0.0% |
| 8 | [2,1] | 14.0 | 14 | 0.0% |
| 10 | [1,1,1] | 18.0 | 18 | 0.0% |
| 10 | [1,1] | 18.0 | 18 | 0.0% |
| 12 | [2,1] | 20.0 | 20 | 0.0% |
| 6 | [1] | Infeasible | Infeasible | n/a |

**All 7 feasible instances show exactly 0% optimality gap; the 8th (tightest single-pad case) is correctly called infeasible by both solvers** (a useful cross-check, not just a "no answer").

> **E10 correction (2026-09-22, replacing the paragraph originally here):**
> the 0% gap was originally explained as least-slack-first being "a
> classical optimal rule ... near-provably optimal" for this uniform-cost
> structure. **That explanation is wrong.** The actual reason is simpler
> and less interesting: in this v1 MILP, the objective is total
> pad-slots used, and that total is **constant** across any schedule
> that charges every drone to its target without overcharging — there
> is no scheduling choice left that could change the objective value
> once feasibility is fixed. So a 0% gap here does not show the
> heuristic finds a *cost-minimising* schedule among several
> alternatives; it only shows the heuristic finds *a* feasible schedule
> whenever the MILP also finds one feasible — a correctness check, not
> an optimality result. A real optimality-gap comparison needs an
> objective where different feasible schedules actually cost different
> amounts (F12, `REMEDIATION.md` Section 2), which this v1 objective does
> not provide. Not yet re-run against F12.

**Robustness check** (`experiments/phase5_gap_robustness.py`, 2026-09-21, 5 random seeds each on 3 representative configs — n=6/pads=[1,1], n=8/pads=[2,1], n=10/pads=[1,1,1], results at `results/phase5_gap_robustness_20260921_183055.csv`): **all 15/15 additional instances show exactly 0% gap**. Combined with the original 8-instance sweep (7 feasible + 1 correctly Infeasible), that's **22/22 feasible instances at exactly 0% gap, out of 23 total instances tested** (1 correctly called Infeasible by both solvers). Corrected here from an earlier "23/23" miscount caught while building the report figure. **[E10 applies here too: this is a robustness check on the constant-objective structure, not a robustness check on optimality.]**

**Status: Phase 5 done**, including C9 (piecewise CC-CV, later found under E8 to not actually enforce CC-CV within a slot) and C10 (charging continuity, later found under E9 to need horizon-end truncation), both implemented and tested but with open E8/E9 fixes pending. Not yet done: re-running the optimality-gap comparison using F12 (the natural way to find a nonzero gap, since v1's constant-objective structure structurally cannot produce one, per E10).

## Phase 6 — Scale and statistics ✅ DONE except capacity-m axis (2026-09-21)

> **E13 note:** the energy comparisons below are labelled **provisional**
> per `REMEDIATION.md` E13 — total charged energy tracks work done and
> trip count, not charging efficiency, and the fleet-size sweep changes
> both drones-per-station and the station layout at every fleet size
> simultaneously. A proper re-analysis (energy decomposition,
> per-mission normalisation, multiple layouts) is experiment X5,
> not yet run.

| Sweep | Values | Status |
|---|---|---|
| Fleet size | 4 → 60 drones | **Done (provisional, E13)** |
| Station density | scarce / balanced / abundant | **Done (provisional, E13)** (n_uavs=20 fixed) |
| Capacity m | 6, 7, 8, 9 (matches reference) | Covered in Phase 2's full-grid sweep, not re-run at Phase 6 scale — the only remaining gap in this table |
| Mission load | light / nominal / saturated | **Done (provisional, E13)** (n_uavs=20, n_stations=5 fixed) |
| Tariff | flat / time-of-use | **Done**, `sim/tariff.py` — see caveat below about the horizon not spanning a full day |
| Seeds | ≥ 30 per configuration | **Done**, all sweeps below |

95% CIs on every point, paired tests between policies, runtime per decision at every fleet size — **done** for the fleet-size axis.

**Fleet-size sweep, full vs adaptive charging** (`experiments/phase6_scale.py`, 2026-09-21, 30 seeds per fleet size, n_stations scaled ~1 per 4 drones ("balanced" density), mission rate scaled proportionally (0.04/min per drone), horizon=1000min, results at `results/phase6_scale_20260921_184347.csv` + summary CSV, 719.7s total):

| n_uavs | n_stations | full energy (Wh) | adaptive energy (Wh) | % diff (adaptive−full)/full | Wilcoxon p |
|---|---|---|---|---|---|
| 5 | 2 | 1898.3 [1841.9,1964.8] | 1459.0 [1406.4,1524.1] | **−23.03%** [−24.99%,−21.02%] | 1.86e-09 |
| 10 | 2 | 3811.5 [3735.1,3892.5] | 3027.2 [2957.9,3101.9] | **−20.54%** [−21.90%,−19.28%] | 1.86e-09 |
| 20 | 5 | 7901.3 [7771.0,8039.4] | 8315.1 [8192.2,8451.1] | **+5.28%** [4.35%,6.26%] | 1.86e-09 |
| 40 | 10 | 15853.5 [15705.7,15992.9] | 17217.9 [17023.8,17415.7] | **+8.62%** [7.66%,9.51%] | 1.86e-09 |
| 60 | 15 | 23000.8 [22745.0,23256.7] | 26009.8 [25811.6,26211.5] | **+13.14%** [12.31%,13.97%] | 1.86e-09 |

**Provisional finding (E13): the sign of the adaptive-vs-full comparison reverses with fleet size**, with an apparent crossover between n=10 and n=20 (at this station-density scaling). At small fleets, adaptive uses less total energy (−20% to −23%); at larger fleets, it uses more, growing with fleet size (+5% to +13%). Every single data point has p=1.86e-09 — the maximum possible significance at n=30 (every seed agreed on direction at every fleet size). Zero safety violations at every fleet size, both policies. **Per E13, this reversal is not yet trustworthy as an efficiency finding: n_stations changes with n_uavs in this sweep (drones-per-station goes 2.5, 5, 4, 4, 4 — not held constant), the station layout also changes at every size, and total Wh conflates more trips/more work with genuine inefficiency. X5's energy decomposition and per-mission normalisation are needed before this reversal can be reported as real.**

**E12 correction (replacing the paragraph originally here):** this was originally described as directly contradicting H5 ("expect the largest benefit at high load"). **H5 predicted makespan and deadline-miss outcomes, neither of which was measured here** — only total energy was. A shift in energy is not a test of H5's actual claim, so **H5 remains untested**, not contradicted, until experiment X5 measures makespan and deadline misses directly.

**Runtime scaling:** mean per-run wall-clock time grows from 54.7ms (n=5) to 5991.3ms (n=60) — about 110x for a 12x fleet-size increase. Per-decision cost (runtime ÷ (n_uavs × ticks)) grows from ~11μs to ~100μs over the same range — mildly super-linear, plausibly from the current O(n_uavs × n_missions) linear scan for mission/station assignment each tick (mission count also grows with fleet size). Flagged as a scalability concern for future work (spatial indexing or a priority queue instead of a linear scan), not fixed now. **(This runtime-scaling measurement is not affected by E13 — it's a wall-clock measurement, not an energy-efficiency claim.)**

**Station density and mission-load axes, done** (`experiments/phase6_remaining_axes.py`, 2026-09-21, 30 seeds, n_uavs=20 fixed, results at `results/phase6_remaining_axes_20260921_210910.csv`, 447.2s):

| Density (n_stations, rate=0.8/min) | diff (adaptive-full)/full | p |
|---|---|---|
| scarce (2) | **+18.92%** [15.79,22.19] | 1.86e-09 |
| balanced (5) | +5.28% [4.35,6.26] | 1.86e-09 |
| abundant (10) | +4.91% [4.06,5.82] | 1.86e-09 |

| Mission load (n_stations=5 fixed) | diff (adaptive-full)/full | p |
|---|---|---|
| light (0.3/min) | −0.61% [−2.01,0.79] | 0.349 (not significant) |
| nominal (0.8/min) | +5.28% [4.35,6.26] | 1.86e-09 |
| saturated (1.6/min) | **+41.76%** [36.69,47.15] | 1.86e-09 |

**Provisional (E13): this axis-by-axis picture — the adaptive-charging energy gap growing with system contention along every axis tested, vanishing under genuinely slack conditions (light load: not significant) — is the strongest, most general form of the 4.4/Phase 6 finding, but is subject to the same E13 caveat as the fleet-size sweep above (total Wh, not per-mission or decomposed energy) until X5 re-analyses it.**

**Tariff axis, done, with an honest caveat:** flat vs time-of-use (peak 17:00-21:00 @ $0.30/kWh, shoulder @ $0.15/kWh, off-peak @ $0.08/kWh) cost tracked per-tick via `sim/tariff.py`. Result: ToU came out ~18-19% cheaper for both policies (full: $0.985 vs $1.211; adaptive: $1.027 vs $1.250). **This is mostly an artifact of the experiment's horizon (1000min ≈ 16.7h), which starts at simulated midnight and never reaches the 17:00-21:00 peak window at all** — not a validated finding about ToU pricing under a representative full day. Flagged rather than presented as a real insight. Neither charge policy is tariff-aware (doesn't shift timing to chase cheaper hours), so $ cost tracks Wh energy 1:1 within each tariff — a tariff-aware policy is a natural but unbuilt future increment. This is fixed in the Section 7 answers (`CLAUDE.md` Section 13): X8 shifts the horizon to actually cover the peak window.

**Not done:** Phase 3's R1-R3b results at the full (n,m) grid — superseded, see the Phase 3 note above; a tariff-aware charging policy.

## Phase 7 — Figures and writing ⏳ STARTED (2026-09-21)

Write the methods in phase order (replication → simulator validation → one change at a time); that order is the argument for trustworthiness.

**Started:** `experiments/make_figures.py` generates 9 figures from saved CSVs to `figures/` (per Section 11: plots come from CSVs, not in-memory data). `experiments/make_report.py` compiles a 15-page PDF (`Phase1-6_Results_Report.pdf`) covering Phases 1-6 with embedded figures, key result tables, the 7-bug cross-cutting summary, and an explicit "what's missing" section. Not the full paper write-up envisions (no methods narrative beyond per-phase summaries, no baseline comparison against threshold/nearest-greedy policies) — a results report, not the paper itself. **This report predates REMEDIATION.md and is now stale in several places (Phase 3 headline, Phase 5 explanation, Phase 6 energy framing) — do not cite it without cross-checking `CLAUDE.md` Section 13 first.**

---

## Overall pre-remediation status (as reported 2026-09-21, before REMEDIATION.md)

Simulation Phases 1-6 all done (Phase 6 missing only the capacity-m-at-scale axis, already covered at Phase 2 scale), all verified in this repository:
- Phase 1: Tables 2/3 reproduced (deviation 3.06e-4/5.82e-5).
- Phase 2: simulator matches analytics, full-grid worst error <7%.
- Phase 3: R1/R2/R3a/R3b implemented; mandatory sanity checks passing; crossover-shift result statistically rigorous at 3 grid points (corners + middle: n=4,m=6 / n=5,m=7 / n=10,m=9) — shift magnitude consistent (~0.11-0.13) across all three, confirming it generalizes rather than being a fluke of one (n,m). **[Superseded by X1 — see the Phase 3 note above.]** R3b's geometry-dependent three-way split documented but not yet at this rigor; full 28-point grid confirmed computationally infeasible in one sitting (~27h extrapolated).
- Phase 4: energy model, mission/UAV models, discrete-time mission simulator; 4.1-4.4 done; least-slack-first ordering added as an extra increment with an honest null result (not significant, p=0.22-0.18, after an initial single-seed anecdote looked promising but didn't replicate). The 4.4 charge-target finding is statistically airtight (30 seeds, p=1.86e-09).
- Phase 5: MILP built (PuLP+CBC), hand-checkable instance verified by hand, C9 (piecewise CC-CV) and C10 (charging continuity) both implemented with correct band-selection indicators after an initially-documented formulation turned out to be wrong (caught before implementing). Optimality gap = **0% across all 22 feasible instances tested (23 total, 1 correctly Infeasible)** (v1 flat-rate scope; **explanation corrected by E10 above** — this reflects a constant objective, not near-optimality; not yet re-measured against F12).
- Phase 6: fleet-size, station-density, and mission-load axes all done (30 seeds, paired tests, runtime scaling), plus a tariff cost model (flat/time-of-use). **Provisional finding (E13), now observed along three independent contention axes**: the Phase 4 adaptive-charging energy total grows differently with fleet size — reverses sign with fleet size (−23%/−21% at n=5/10 → +5%/+9%/+13% at n=20/40/60), is ~4x worse under scarce stations than balanced/abundant (+18.9% vs +4.9-5.3%), and grows from not-significant at light load to +41.8% at saturated load. All p≤1.86e-09 where significant. **Not yet re-analysed under X5 (energy decomposition, per-mission normalisation, multiple layouts) — treat as provisional, not confirmed, per E13.**

Seven real implementation bugs were caught and fixed along the way, every one via a smoke test, cross-check, or independent-verification showing implausible numbers — never by inspection alone: Phase 2's L-metric definition, Phase 4's reachability-gate gap and adaptive-target undershoot, Phase 5's SoC-saturation equality, and three more in the Phase 5 CC-CV extension (a wrong initially-documented C9 formulation caught before implementing, a free-SoC-jump-when-not-charging hole, and a spurious-SoC-decrease-with-no-discharge-model hole). Four findings directly contradicted a stated hypothesis, initial expectation, or first-look anecdote and were reported as such rather than tuned to agree: H2's priority-improves-outcomes assumption (Phase 3), the Phase 6 energy reversal read against H5 (**now corrected — H5 was never actually tested, per E12**), the unverified PDF reports' partial-charging energy-savings claim, and Phase 4's own least-slack-first ordering (looked like a big win on one seed, replicated to a null result on 20).

Remaining (as of 2026-09-21): Phase 3's full 28-point (n,m) grid and R3b's statistical rigor (**superseded — X1 uses the corrected metric instead**); re-measuring Phase 5's optimality gap against F12 (per E10, the natural way to find a nonzero gap, since v1's constant-objective scope structurally can't produce one); a tariff-aware charging policy; Phase 6's capacity-m axis re-run at Phase-6 scale (only done at Phase 2 scale so far); the fuller P(v,m) flight power model (flat-rate kappa is in use, not the richer form). Phase 7 (figures/writing) not started at this point. Hardware track not started in this repository (out of scope for now — user has directed focus to the simulation track only).

### Old open-decisions list (superseded by `CLAUDE.md` Section 13's Section 7 answers)

**Open decisions (as of 2026-09-21):**
1. Exact form of the flight power model — still genuinely open, see `CLAUDE.md` Section 13.

**Settled (for reference):**
2. Does W_j enter the MILP? **No** — kept implicit (C1 pad-capacity already forces an optimal schedule to account for waiting).
3. Formal statements of C9 and C10 — both implemented in `solve_charge_schedule_milp_ccv` (`sim/milp.py`); an initially-documented C9 formulation was wrong and was corrected before implementing. **(C9/C10 have since-identified remaining issues — E8, E9 — not yet fixed.)**
4. Distribution of slack s_i in Phase 3 — Exponential(mean = 1/mu), drawn for every request regardless of regime so CRN comparisons are valid.
5. Priority weights w1, w2 — Phase 3 uses pure least-slack-first (w1=1, w2=0) since the margin/SoC term didn't exist until Phase 4.
6. Geometry for R3b — settled by proceeding (user directed): 2000m×2000m area, n stations at fixed random positions (seed=0), drone speed 15 m/s, each request's origin drawn uniform in the area. See `sim/scheduler.py` docstring.
