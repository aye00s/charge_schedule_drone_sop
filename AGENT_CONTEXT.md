# Agent context: Queue-Aware Charge Scheduling for UAV Fleets

Technical brief for an agent with no prior context on this repository.
Covers the formulas, model structure, and methodology actually implemented
and validated (not aspirational). Full narrative detail and phase-by-phase
status live in `CLAUDE.md`; this document exists to transfer the math and
method without requiring that whole file to be read first.

## 1. What this project is

A discrete-time / discrete-event simulation study of **charge scheduling
for UAV fleets**: N drones, M charging stations (each with a fixed pad
count), missions with deadlines, limited batteries, non-linear (CC-CV)
charging. The research question: a reference paper (Wang et al. 2020)
found a crossover load point ρ* below which one concentrated charging hub
beats spread-out distributed pads, and above which distributed wins — but
that result assumes **random (Poisson) arrivals and FCFS service**. This
project tests whether the crossover survives once arrivals are the output
of a **deadline-aware scheduler** instead of a random process.

## 2. Reference paper formulas (Phase 1 — reproduced exactly)

Wang Y Z, Xu G N, Wang S, Li Z J, Cai R. "Optimization of charging queuing
of UAV swarming." *Acta Aeronautica et Astronautica Sinica*, 2020,
41(10):323928.

Setup: distributed = n independent M/M/1/m queues, each fed λ/n.
Concentrated = one M/M/n/**nm** queue (capacity is nm, not m — a common
transcription error to avoid). ρ = λ/(nμ).

For ρ ≠ 1:

**Distributed queue length** (Eq. 11):
L_d = ρ[(m-1)ρ^(m+1) − mρ^m + ρ] / [(1-ρ)(1-ρ^(m+1))]
At ρ=1: L_d = (m²-m) / (2(m+1))

**Concentrated empty-system probability** (Eq. 15):
P̂0 = [Σ_{k=0}^{n-1} (nρ)^k/k! + (nρ)^n/n! · (1-ρ^(nm-n+1))/(1-ρ)]^-1

**Concentrated blocking probability** (Eq. 16):
P_nm = (n^n ρ^nm / n!) · P̂0

**Concentrated queue length** (Eq. 13):
L_c = [n^n ρ^(n+1) P̂0 / (n!(1-ρ)²)] · [1 - (nm-n+1)ρ^(nm-n) + (nm-n)ρ^(nm-n+1)]

**Distributed wait time, 1/λ factored out** (Eq. 18):
t_d = nρ[(m-1)ρ^(m+1) − mρ^m + ρ] / [(1-ρ)(1-ρ^m)]

**Concentrated wait time, 1/λ factored out** (Eq. 19):
t_c = [n^n ρ^(n+1) P̂0 / (n!(1-ρ)²(1-P_nm))] · [1 - (nm-n+1)ρ^(nm-n) + (nm-n)ρ^(nm-n+1)]

All have ρ=1 closed forms (division by zero otherwise); switch when
|ρ-1| < 1e-12. Implemented in `phase1_baseline.py`. Validated against the
paper's published tables to a stable residual of 3.06e-4 (Table 2) / 5.82e-5
(Table 3) — confirmed by sweeping bisection tolerance from 1e-4 to 1e-12
and finding the deviation plateaus rather than shrinking to zero, i.e. the
residual is the paper's own rounding, not our under-convergence.

## 3. Discrete-event simulator (Phase 2 — `sim/core.py`)

Event-driven M/M/c/K simulation validating the analytics before changing
any assumption. Key implementation facts, each the product of a real bug
caught by cross-checking against Section 2's formulas:

- **L is the number WAITING for a server (queue length excluding those in
  service), not total-number-in-system.** The first implementation
  measured total-in-system and was off by up to 10x. Confirmed by
  comparing both definitions against the analytics side by side.
- **Wait time `t`** is rescaled by the *total* arrival rate λ (not the
  per-queue rate λ/n) to match the paper's "1/λ factored out" convention —
  i.e. `t_sim = mean_wait_seconds * lambda_total`.
- Warm-up fraction discarded before collecting statistics (default 10% of
  horizon).
- Validated on the full 7×4 (n,m) grid × ρ∈{0.6,0.8,1.0,1.2} × 3 seeds:
  worst relative error L_d=2.9%, L_c=6.5%, t_d=3.2%, t_c=6.4%.

## 4. Scheduler regimes (Phase 3 — `sim/scheduler.py`)

Distributed-layout simulator (n single-server M/M/1/m stations) with
independently configurable **routing** and **service order**:

- **Routing**: `fixed_split` (uniform random station choice per arrival —
  statistically equivalent to n independent λ/n streams, i.e. the paper's
  assumption) | `jsq` (join-shortest-queue: route to the station with
  fewest drones currently waiting) | `jsq_travel` (JSQ + travel-time cost:
  `J_ij = waiting_count[j]/μ + travel_time(origin, station_j)/speed`,
  combining queue delay and travel time in a single time-denominated cost,
  per the project's Section 5.1 design: reachability is a hard gate
  evaluated first, distance and queue delay are costs combined without
  weight-tuning because both are already measured in time units).
- **Order**: `fcfs` (arrival order) | `priority` (earliest-deadline-first:
  `deadline = arrival_time + slack`, `slack ~ Exponential(mean=1/μ)` drawn
  for *every* request regardless of regime, so seeded runs are directly
  comparable via common random numbers).

Four regimes tested: **R1** (fcfs, fixed_split — reproduces the paper),
**R2** (priority, fixed_split — isolates service-order effect alone),
**R3a** (priority, jsq), **R3b** (priority, jsq_travel).

**Two sanity checks are mandatory before any Phase 3 result counts:**
1. *Slack-zero reduction*: with slack=0, the engine must reproduce the
   Phase 1/2 analytics (deadline=arrival_time collapses priority order to
   FCFS order exactly).
2. *Conservation check (Kleinrock)*: R2 must match R1 on average L and
   wait — reordering by a priority independent of service duration cannot
   change the number-in-system process, only per-drone outcomes. If R2 ≠
   R1 on averages, that is a bug, not a finding.

Both pass. Headline result: R3a shifts the concentrated-vs-distributed
crossover ρ* left by a consistent amount (~0.11-0.13 in ρ) across three
tested (n,m) grid points — confirmed with 30-seed bootstrap CIs via
`sim/stats.py::estimate_crossover_ci` (linear interpolation between
bracketing ρ grid points, bootstrapped over seeds preserving CRN pairing).

## 5. Energy and mission model (Phase 4 — `sim/energy.py`, `sim/mission_sim.py`)

Discrete time stepping, dt=1 minute. UAVs fly real missions (Poisson
releases, random origin/destination), draining batteries, so charge
requests are **emergent**, not an exogenous input.

**Flight energy** (flat-rate model, Section 4.3's first candidate):
E = κ · distance, **κ = 0.01 Wh/m** (NOT the paper's own example κ=0.5
Wh/m — that value combined with a 90Wh battery gives only 180m of total
range, physically unusable; κ=0.01 Wh/m is grounded in typical
small-quadcopter cruise power/speed, giving ~9km range at full charge).
The richer P(v,m) = β0 + β1·m + β2·v² + β3/v form (Section 4.3's second
candidate) is **not implemented** — needs hardware-calibrated
coefficients, an open decision.

**SoC recurrence**: S(t+1) = S(t) - e(t)/B + η·r_j·Δt/B·x_ijt (charging
increases SoC by rate r_j when x_ijt=1, flight decreases it by energy/B).

**CC-CV charging curve** (3-band piecewise, Section 4.3 defaults):
- 0-70% SoC: 200 W
- 70-90% SoC: 120 W
- 90-100% SoC: 50 W

`soc_after_charging(soc, minutes, battery_wh)` steps band-by-band so a
step crossing a boundary uses the correct rate in each part.
`time_to_reach_target_min` is the closed-form inverse. Confirmed
non-exponential (coefficient of variation 0.031 vs. 1.0 for exponential)
— the paper's M/M/c formulas do not apply once this is in the loop
(M/G/c instead).

**Reachability gate** (feasibility, evaluated before any departure):
`_reachable_with_return` requires enough energy to (a) reach the
destination with ≥σ=0.20 remaining AND (b) subsequently reach *some*
charging station from there. Checking only (a) — the literal reading of
constraint C8 — lets a mission legally strand a drone at exactly σ with
nowhere reachable afterward; this was a real bug caught via 1410 safety
violations in a smoke test.

**Two charge-target policies**, isolating one variable (Section 7
principle: change one assumption at a time):
- `full`: always charge to 100%.
- `adaptive`: charge to the SoC needed for the most demanding mission
  releasing within a 30-minute lookahead window (plus σ margin), floored
  at `RECHARGE_TRIGGER_SOC + 0.05 = 0.40` (without the floor, the target
  can undershoot the drone's own recharge trigger, causing an infinite
  zero-duration charge loop — a real bug caught via 15,000+ sessions for
  15 drones). Tops off fully if no mission is on the horizon.

**Headline finding**: adaptive charging's energy cost relative to `full`
is not a fixed sign — it depends on system contention along three
independent axes (all p≤1.86e-09 where significant, 30 seeds):
- Fleet size: saves 20-23% at n=5-10, costs 5-13% more at n=20-60
  (crossover between n=10 and n=20).
- Station density: costs ~4x more under scarce stations (+18.9%) than
  balanced/abundant (+4.9-5.3%).
- Mission load: not significant at light load, costs 41.8% more at
  saturated load vs. nominal's 5.3%.

**Priority ordering** (`order='priority'` in `run_mission_sim`): mission
assignment by deadline-t ascending (not release order), pad queue served
by lowest battery margin (soc-σ) first — Section 6's slack/margin
priority, now meaningful with a real SoC model. 20-seed paired test found
**no statistically significant benefit** over FCFS at any load tested
(p=0.18-0.22) — a single-seed anecdote initially looked like a large win
and did not replicate.

## 6. MILP formulation (Phase 5 — `sim/milp.py`, PuLP + CBC)

**v1 (base, validated on a hand-checkable instance):**
Variables: `x[i,j,t] ∈ {0,1}` (drone i charges at station j in slot t),
`S[i,t] ∈ [σ,1]` (SoC at start of slot t).
Constraints: pad capacity `Σ_i x[i,j,t] ≤ pads[j]`; one station at a time
`Σ_j x[i,j,t] ≤ 1`; SoC recurrence **as an inequality**
`S[i,t+1] ≤ S[i,t] + Σ_j (η·rate_w[j]·dt/60/battery[i])·x[i,j,t]`
(critically NOT equality — see bug note below); hard deadline
`S[i,deadline[i]] ≥ required_soc[i]`. Objective: minimize total
pad-occupancy `Σ x[i,j,t]` (a congestion/wear proxy).

**Bug and fix (equality vs. inequality)**: the recurrence was first an
equality. On an 8-drone instance the MILP reported Infeasible while an
independently-verified-feasible heuristic solution existed — proof of a
MILP bug (an exact solver cannot correctly call something infeasible when
a feasible solution provably exists). Root cause: the equality forced SoC
to mathematically exceed 1.0 whenever a charging decision would overshoot
full, instead of saturating. Fixed with `<=`; sound because the objective
only rewards using less charging, never rewards a lower SoC, so the
solver has no incentive to under-report.

**C9 (piecewise CC-CV), `solve_charge_schedule_milp_ccv`**: proper
band-selection indicator variables `z[i,t,l]` (one active band per
drone/slot), Big-M linking S[i,t] to its band
(`S[i,t] ≥ lo_l - M(1-z)`, `S[i,t] ≤ hi_l + M(1-z)`), and a further Big-M
linking the charging increment to both the charge decision and the
active band:
`S[i,t+1] ≤ S[i,t] + rate_l·η·dt/60/battery[i] + M(2 - x_total[i,t] - z[i,t,l])`.
An **earlier documented version of this formulation was wrong** —
applying every band's rate as a simultaneous bound regardless of actual
SoC would force every drone onto the slowest band no matter how low their
SoC is; caught before implementing, not after. Two more real bugs found
while building the corrected version: (a) without an extra
`S[i,t+1] ≤ S[i,t] + M·x_total[i,t]` constraint, not-charging leaves SoC
completely unconstrained (all band constraints simultaneously Big-M
relaxed) — caught via objective=0 with zero charging sessions on an
instance that needs real charging; (b) without an explicit
`S[i,t+1] ≥ S[i,t]`, nothing prevents a spurious SoC decrease between
slots (no discharge component in this scheduling-only model) — caught via
SoC dropping mid-schedule with no charging to explain it.

**C10 (charging continuity / minimum dwell)**: needs no Big-M — since
`Σ_j x[i,j,t]` is binary, the rising-edge difference directly forces
continuity: `x_total[i,t] - x_total[i,t-1] ≤ x_total[i,t']` for every t'
in the dwell window.

**Comparable heuristic** (`solve_charge_schedule_heuristic`): greedy
least-slack-first, solving the *same* discrete problem (needed for a fair
apples-to-apples optimality gap — this heuristic still assumes a constant
rate internally, so it has NOT yet been compared against the CC-CV MILP
version).

**Optimality gap result**: 22/22 feasible instances (23 tested, 1
correctly Infeasible on both solvers) show **exactly 0% gap**. Explained,
not just observed: in this v1 uniform-cost scope every pad-slot costs
exactly 1 unit regardless of drone/station, so the only real decision is
*who* gets scarce pad-time *when* — least-slack-first is close to
provably optimal for this specific problem structure. Should not be
generalized to "the heuristic is always near-optimal" — a nonzero gap is
expected once costs become heterogeneous (tariffs, travel, the CC-CV
curve itself in the comparison).

## 7. Statistics infrastructure (`sim/stats.py`)

- `bootstrap_ci(data, stat_fn=mean, n_boot=2000, alpha=0.05)`: percentile
  bootstrap, resampling with replacement.
- `paired_test(a, b)`: Wilcoxon signed-rank on paired (same-seed) samples.
- `estimate_crossover_ci(rho_grid, values_a_by_rho, values_b_by_rho)`:
  finds where mean(a)-mean(b) crosses zero via linear interpolation
  between bracketing ρ grid points, bootstraps over the seed index
  (jointly for a and b at every ρ, preserving CRN pairing) for a CI on
  the crossover location. Deliberately not plain bisection on noisy
  simulation output.

## 8. Methodology principles actually followed

1. **Validation chain**: reproduce the reference model exactly (Phase 1)
   → confirm the simulator matches it (Phase 2) → only then relax
   assumptions (Phase 3+).
2. **Change one assumption at a time**: e.g. Phase 3 splits R3a
   (routing/timing change) from R3b (+ travel geometry) specifically so a
   result difference is attributable to exactly one cause; Phase 4
   isolates the charge-target variable from the ordering variable.
3. **Common random numbers (CRN)**: every regime/policy draws the same
   underlying randomness (arrivals, slack, service times) for a given
   seed, so paired comparisons have low variance and paired significance
   tests are valid.
4. **≥30 seeds, 95% CIs, paired Wilcoxon tests** for any claim treated as
   final — single-seed or 5-seed results are explicitly exploratory and
   were repeatedly caught giving misleading anecdotes (e.g. a 1-seed
   priority-ordering "win" that a 20-seed test showed was not
   significant).
5. **Time-weighted, not event-weighted, averages** for queue length.
6. **Warm-up discard** before collecting statistics.
7. **Never fabricate or tune to match a hypothesis.** Every numeric claim
   in this project comes from code actually run, with results reported
   even when they contradict a stated hypothesis (H2, H5) or an earlier
   unverified external claim.
8. **Report contradictions and null results plainly** rather than
   smoothing them into the expected narrative — the project's strongest
   results (the fleet-size sign reversal, the 0% MILP gap with an actual
   mechanism) came from taking anomalous-looking output seriously enough
   to explain it rather than discard it.

## 9. Known open items (not fabricated as done)

- Full 28-point (n,m) grid at 30-seed crossover rigor: infeasible in one
  sitting (~27h extrapolated); 3 representative points done instead.
- R3b not yet brought to 30-seed rigor; its three-way load-dependent
  split is suspected to be an artifact of one specific random station
  layout, not yet confirmed with a second layout.
- CC-CV MILP optimality gap not yet re-measured (heuristic needs a
  matching piecewise-rate upgrade first).
- Tariff cost *tracking* exists (`sim/tariff.py`, flat vs. time-of-use)
  but no tariff-*aware* policy that acts on price.
- Richer P(v,m) flight power model: open decision, needs hardware-
  calibrated coefficients, not implemented.
- Phase 7 (paper write-up) only partially started: a results report
  (`Phase1-6_Results_Report.pdf`) exists; the full methods narrative does
  not.
