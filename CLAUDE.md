# CLAUDE.md — Queue-Aware Charge Scheduling for UAV Fleets

> **To the Claude agent working in this repository:** This file is the full context for a PhD research project. Place it at the repository root as `CLAUDE.md` so it is loaded automatically at the start of every session. Read all of it before writing or running any code.
>
> You can read files, write code, and run it. Use that: **every claim about results, test outcomes, or pass gates must come from code you actually ran in this repository, with the real output shown.** Never invent, estimate, or "expect" numbers in place of running the code.
>
> `phase1_baseline.py` at the repository root is the working, validated code for Phases 1 and 2. Reuse its functions rather than rewriting them.
>
> Follow the agent workflow in Section 0, the methodology in Section 7, the conventions in Section 11, and the rules in Section 15.

---

## 0. Agent workflow

### 0.1 At the start of every session
1. Read this file fully, especially Section 13 (current status and open decisions).
2. Inspect the repository (`ls`, `git status`, `git log --oneline -10`) to see what exists and what changed since the status in Section 13 was last updated.
3. Run the existing test suite (`pytest -q`) before changing anything, so you know the starting state. If tests fail at the start, report that to the user before doing new work.

### 0.2 How to work
- **One phase at a time.** Do not start a phase until the previous phase's pass gate has been met *by running its tests*.
- **Plan before large changes.** For any new phase or module, first give the user a short plan (files to create, functions, tests, which open decisions it touches) and wait for approval.
- **Open decisions (Section 13 and 14.10):** if one affects the code you are about to write, ask the user. Do not silently pick a default. If the user tells you to proceed with a default, record it in Section 13.
- **Tests first for each phase.** Write the phase's tests and sanity checks, run them, then write the experiment code.
- **Small runs before big runs.** Run every experiment first with a tiny configuration (few seeds, short horizon, small grid) to check it works and to estimate runtime. Tell the user the estimated runtime of the full run before launching anything longer than ~10 minutes.
- **Raw results are never overwritten.** Each run writes a new timestamped CSV under `results/`. Figures are generated from saved CSVs only.
- **Commit at checkpoints** with clear messages (e.g., `phase3: add slack-zero sanity check (passing)`), if the user uses git.

### 0.3 Reporting
When you finish a task, report:
- what you changed (files and functions),
- the exact commands you ran,
- the actual output (test results, key numbers), copied from the run, not paraphrased into rounder numbers,
- anything that failed, looked suspicious, or is untested,
- which pass gate (if any) is now met.

If a result contradicts a hypothesis in Section 9, report it plainly. Do not re-tune parameters to make it agree.

### 0.4 Keeping this file current
After a pass gate is met or an open decision is settled, update Section 13 (and the phase's status in Section 8 or 14.7) with the date, what was done, and the key validated numbers. Show the user the diff to this file. This file is the project's memory between sessions, so keep it accurate.

Also update `PROGRESS.md` at the repository root in the same pass — it's the at-a-glance phase-by-phase checklist (checkboxes only, no narrative detail; the numbers and reasoning stay here in CLAUDE.md). Check a box the moment its pass gate is met by a real test run, not before.

### 0.5 Environment
- Python 3.10+ in a virtual environment; keep dependencies in `requirements.txt` and add to it when you install something.
- Default solver: HiGHS (`highspy`) or CBC via PuLP; do not assume Gurobi is installed unless the user confirms a licence.
- Firmware (hardware track) targets ESP32 with PlatformIO. You can write and compile firmware if PlatformIO is installed, but **you cannot test it on real hardware**. Say so every time, and never mark a hardware pass gate as met; only the user can do that after physical testing.

---

## 1. Project summary

This is part of a PhD project (called "Part A") on **charge scheduling for UAV (drone) fleets**. A fleet of drones performs missions with deadlines and shares a limited number of charging pads. Batteries are limited, charging takes time, and pads can only serve a fixed number of drones at once. A **scheduler** decides, for each drone, **which pad it charges at, when, and to what state of charge (SoC)**, so that missions finish on time, cheaply, and without any drone ever dropping below a safe battery reserve.

The project has two tracks:

1. **Simulation track (the paper).** Formulate the problem mathematically, build a simulator, and compare our scheduling approach against a published reference paper and several baselines. This is the main focus and what you will write code for.
2. **Hardware track (a physical charging pad prototype).** Provides real measurements to calibrate the charging curve, charging efficiency, and flight energy model, and to check predicted waiting times. Fully described in Section 14, including components, firmware, development phases H0–H8, and code to be written.

---

## 2. Research question and contribution

### 2.1 The core question

A reference paper (Wang et al., 2020, Section 3) compared two layouts of charging pads and found a **crossover point**: below a certain load, one shared hub (concentrated charging) is better; above it, spread-out individual pads (distributed charging) are better. That result assumes drones arrive **randomly** (Poisson process) and are served **first-come-first-served (FCFS)**.

**Our question:** Does that crossover survive when drone arrivals at pads are not random but **controlled by a deadline-aware scheduler**?

### 2.2 Why this is a contribution

- We are not competing with the reference paper's numbers. We are testing whether its **conclusion** holds once an assumption it did not examine is relaxed.
- In a scheduled fleet, the arrival process at the pads is an **output of the scheduler, not a random input**. Applying Poisson-arrival queueing theory to a controlled fleet is questionable; this is the honest core of the contribution.
- Our model is also richer: individual drone SoC, missions, deadlines, travel energy, non-linear (CC–CV) charging, a safe reserve, and an actual decision output. The reference paper produces performance estimates; we produce **assignment decisions**.
- Our waiting time at each pad is **deterministic and computable** from the reservation list, not a steady-state average.

### 2.3 What we are NOT claiming

We do not claim "more accurate" results than the reference paper on its own problem. Its analytical results are exact under its assumptions. We claim higher fidelity to real operations and a decision-producing method.

---

## 3. Reference paper (full technical detail)

**Citation:** WANG Y Z, XU G N, WANG S, LI Z J, CAI R. "Optimization of charging queuing of UAV swarming." *Acta Aeronautica et Astronautica Sinica*, 2020, 41(10): 323928. DOI: 10.7527/S1000-6893.2020.23928.

### 3.1 Their setup

| Element | Their choice |
|---|---|
| Distributed charging | *n* independent M/M/1/*m* queues; each receives arrival rate λ/*n* |
| Concentrated charging | One M/M/*n*/*nm* queue. **Total capacity is *nm*, not *m*.** |
| Service intensity | ρ = λ/(*n*μ), the same for both layouts |
| Sweep | ρ ∈ [0, 2] |
| Capacity *m* | 6, 7, 8, 9 |
| Platforms *n* | 4 to 10 |
| Indicators | Average queue length *L*; average waiting time *t* (with 1/λ factored out) |
| Crossover | Found by bisection, precision 1e-4 |
| Tool | MATLAB, analytical only, no simulation, no decisions |

What they did **not** model: drone identity, SoC, missions, deadlines, travel, non-linear charging, or any scheduling decision.

### 3.2 Their equations (as implemented and validated)

Let ρ = λ/(nμ). For ρ ≠ 1:

**Distributed, average queue length (Eq. 11):**
$$L_d = \frac{\rho\left[(m-1)\rho^{m+1} - m\rho^{m} + \rho\right]}{(1-\rho)(1-\rho^{m+1})}$$
At ρ = 1: $L_d = \dfrac{m^2 - m}{2(m+1)}$

**Concentrated, empty-system probability (Eq. 15):**
$$\hat P_0 = \left[\sum_{k=0}^{n-1}\frac{(n\rho)^k}{k!} + \frac{(n\rho)^n}{n!}\cdot\frac{1-\rho^{nm-n+1}}{1-\rho}\right]^{-1}$$
At ρ = 1: $\hat P_0 = \left[\sum_{k=0}^{n-1}\frac{n^k}{k!} + \frac{n^n}{n!}(nm-n+1)\right]^{-1}$

**Concentrated, blocking probability (Eq. 16):**
$$P_{nm} = \frac{n^n \rho^{nm}}{n!}\hat P_0$$

**Concentrated, average queue length (Eq. 13):**
$$L_c = \frac{n^n\rho^{n+1}\hat P_0}{n!(1-\rho)^2}\left[1 - (nm-n+1)\rho^{nm-n} + (nm-n)\rho^{nm-n+1}\right]$$
At ρ = 1: $L_c = \dfrac{n^n}{2\,n!}(nm-n)(nm-n+1)\hat P_0$

**Distributed, average waiting time, 1/λ factored out (Eq. 18):**
$$t_d = \frac{n\rho\left[(m-1)\rho^{m+1} - m\rho^m + \rho\right]}{(1-\rho)(1-\rho^m)}$$
At ρ = 1: $t_d = \dfrac{n(m-1)}{2}$

**Concentrated, average waiting time, 1/λ factored out (Eq. 19):**
$$t_c = \frac{n^n\rho^{n+1}\hat P_0}{n!(1-\rho)^2(1-P_{nm})}\left[1 - (nm-n+1)\rho^{nm-n} + (nm-n)\rho^{nm-n+1}\right]$$
At ρ = 1: $t_c = \dfrac{n^n \hat P_0}{2\,n!(1-P_{nm})}(nm-n)(nm-n+1)$

Notes:
- The waiting-time denominators differ from the queue-length ones because waiting is averaged over **admitted** drones only (Little's law with effective arrival rate λ(1 − P_block)).
- Near ρ = 1 the general formulas divide by zero; switch to the ρ = 1 forms when |ρ − 1| < 1e-12.

### 3.3 Their results (ground truth for validation)

**Table 2 — queue-length crossover ρ\*** (rows *n*, columns *m* = 6, 7, 8, 9):

| n | m=6 | m=7 | m=8 | m=9 |
|---|---|---|---|---|
| 4 | 0.70751953125 | 0.73193359375 | 0.75205078125 | 0.76884765625 |
| 5 | 0.72783203125 | 0.75048828125 | 0.76904296875 | 0.78447265625 |
| 6 | 0.74315703125 | 0.76455078125 | 0.78193859375 | 0.79619140625 |
| 7 | 0.75576171875 | 0.77568359375 | 0.79208984375 | 0.80556640625 |
| 8 | 0.76611328125 | 0.78486328125 | 0.80029249675 | 0.81318359375 |
| 9 | 0.77470703125 | 0.79267578125 | 0.80751953125 | 0.81982421875 |
| 10 | 0.78193359375 | 0.79931640625 | 0.81357421875 | 0.82529296875 |

**Table 3 — waiting-time crossover ρ\***:

| n | m=6 | m=7 | m=8 | m=9 |
|---|---|---|---|---|
| 4 | 1.019188720703125 | 1.013821923828125 | 1.010406689453125 | 1.008089208984375 |
| 5 | 1.014553759765625 | 1.010406689453125 | 1.007845263671875 | 1.006137646484375 |
| 6 | 1.011504443359375 | 1.008211181640625 | 1.006259619140625 | 1.004795947265625 |
| 7 | 1.009430908203125 | 1.006747509765625 | 1.005039892578125 | 1.003942138671875 |
| 8 | 1.007967236328125 | 1.005649755859375 | 1.004308056640625 | 1.003332275390625 |
| 9 | 1.006869482421875 | 1.004917919921875 | 1.003698193359375 | 1.002844384765625 |
| 10 | 1.006015673828125 | 1.004308056640625 | 1.003210302734375 | 1.002478466796875 |

Bisection brackets that work: queue length in [0.7, 0.9]; waiting time in [1.0001, 1.125].

**Interpretation:** below ρ\*, concentrated is better; above it, distributed is better. Note the queue-length crossover (≈0.71–0.83) and the waiting-time crossover (≈1.00–1.02) disagree. The paper does not explain this.

**Note on Table 2's L_d (added 2026-09-22, from `REMEDIATION.md` E1):** Eq. 11's L_d is **one distributed queue's** average length (it has no dependence on n, since every one of the n queues is statistically identical) — not the distributed layout's **total** queue across all n pads. Table 2's crossover therefore compares one pad's queue to the whole pooled hub's queue, which is not a like-for-like system-wide comparison. This project's own like-for-like total-queue crossover (n·L_d vs L_c, computed analytically, Section 13) lands at ρ≈0.98-1.00 for the three (n,m) points checked — much closer to Table 3's waiting-time crossover (≈1.00-1.02) than to Table 2's own per-queue crossover (≈0.71-0.83). This is a plausible explanation for why Tables 2 and 3 disagree: t (Table 3) is already system-wide and like-for-like (t_d = n·L_d/(1−P_block)), while L_d (Table 2) is not. Table 2 is used in this project only as "replication of the reference metric," not as a like-for-like comparison — see Section 13.

---

## 4. Our mathematical model

### 4.1 Assumptions

- A1. Time is divided into uniform slots of length Δt.
- A2. Battery ageing is negligible over the horizon.
- A3. Flight energy is deterministic given speed and payload.
- A4. Charging can only be interrupted at slot boundaries.
- A5. In any slot a drone either flies or charges, never both.
- A6. A drone waiting in a queue has landed and uses **no** propulsion energy.

### 4.2 Notation

| Symbol | Meaning |
|---|---|
| I = {1..N} | Drones (UAVs) |
| J = {1..M} | Charging stations |
| K | Missions |
| T | Time slots |
| L | Segments of the piecewise-linear charging curve |
| B | Usable battery capacity (Wh) |
| c_j | Number of pads at station j |
| r_j | Charging power at station j (W) |
| η | Charging efficiency |
| σ | Safe SoC reserve (e.g., 0.20) |
| d_k, ρ_k | Deadline and release time of mission k (this ρ_k is unrelated to service intensity ρ) |
| π_jt | Electricity tariff at station j, slot t |
| τ_ij, e_ij | Travel time and travel energy from drone i to station j |
| α, β, γ | Objective weights |
| x_ijt ∈ {0,1} | Drone i occupies a pad at station j in slot t |
| y_ik ∈ {0,1} | Mission k is assigned to drone i |
| S_i(t) ∈ [σ, 1] | SoC of drone i at start of slot t |
| C_max | Makespan |
| T_k ≥ 0 | Tardiness of mission k |
| W_j(t) | Deterministic waiting time at station j (queue extension) |
| Q_j(t) | Ordered reservation list at station j |

### 4.3 Energy models

Flight power (β coefficients to be calibrated on real hardware, not yet measured — an alternative form a0 + a1·m^(3/2) + a2·v² + a3·v³ + a4/v also appears in project notes; the exact form is still genuinely open, see Section 13):
$$P(v,m) = \beta_0 + \beta_1 m + \beta_2 v^2 + \frac{\beta_3}{v}$$

Leg energy from p to q:
$$E_{pq} = P(v,m)\frac{\lVert p-q\rVert}{v} + E_{to} + E_{land}$$

**Current default (settled 2026-09-22, Section 13's Section 7 answers): a flat rate, E = κ · distance, with κ = 0.01 Wh/m** (not the κ = 0.5 Wh/m originally sketched here as an example — that value, combined with a ~90Wh battery, gives only 180m of total range, unusable at any realistic mission-area scale; κ = 0.01 Wh/m is physically grounded from typical small-quadcopter cruise power/speed, ~9km range at full charge; note this project-internal correction is *not* attributed to Wang et al., who have no energy model of their own). `E_to = E_land = 0` (logged as an assumption). Code exposes an `ENERGY_MODEL="flat"|"power"` switch (`sim/energy.py`) so the P(v,m) form above is ready to use once real β0-β3 values exist from hardware calibration (Section 14.8); only `"flat"` has been validated against simulation results so far.

SoC recurrence:
$$S_i(t+1) = S_i(t) - \frac{e_i(t)}{B} + \frac{\eta\, r_j\,\Delta t}{B}x_{ijt}$$

Non-linear CC–CV charging via L piecewise-linear upper bounds (keeps the model a MILP):
$$S_i(t+1) \le S_i(t) + a_\ell\Delta t + b_\ell \quad \forall \ell \in L$$

Three-band approximation, implemented and in active use in `sim/energy.py` (replace with measured data once hardware calibration exists):

| SoC band | Effective charging power |
|---|---|
| 0–70% | 200 W |
| 70–90% | 120 W |
| 90–100% | 50 W |

### 4.4 Objective

**Current form (settled 2026-09-22, Section 13's Section 7 answers — this is F12 in `REMEDIATION.md` Section 2, replacing the originally-sketched raw/unnormalised form below):**
$$\min Z = \alpha \frac{C_{max}}{T_{horizon}} + \beta \frac{\sum_{i,j,t}\pi_{jt} r_j \Delta t\, x_{ijt}}{\pi_{flat} \cdot E_{total\_mission}} + \gamma \frac{\sum_k T_k}{n_k \cdot \bar{T}_{mission}}$$
with α = β = γ = 1 applied to the three **normalized** terms above (C_max divided by the horizon length; energy cost divided by flat-price × total mission energy; total tardiness divided by number-of-missions × mean mission duration) — not to the raw, differently-scaled quantities a naive reading of the formula below would combine. Flat tariff (π_jt = constant) for all main experiments and the MILP gap; time-of-use tariff only in X8, with the horizon shifted to actually cover the 17:00-21:00 peak window (the pre-remediation Phase 6 tariff experiment's horizon never reached peak hours — see `HISTORY.md`).

Originally-sketched raw form (superseded by the normalized version above, kept for reference since C6/C7 below still use its unnormalized C_max/T_k symbols):
$$\min Z = \alpha C_{max} + \beta\sum_{i,j,t}\pi_{jt} r_j \Delta t\, x_{ijt} + \gamma\sum_k T_k$$

### 4.5 Constraints

- **C1 Pad capacity:** Σ_i x_ijt ≤ c_j for all j, t
- **C2 Single location:** Σ_j x_ijt ≤ 1 for all i, t
- **C3 Safe reserve:** S_i(t) ≥ σ
- **C4 SoC bounds:** σ ≤ S_i(t) ≤ 1
- **C5 Mission assignment:** Σ_i y_ik = 1 for all k
- **C6 Tardiness:** T_k ≥ C_k − d_k, T_k ≥ 0
- **C7 Makespan:** C_max ≥ C_k for all k
- **C8 Reachability:** x_ijt = 1 ⇒ S_i(t − τ_ij) ≥ σ + e_ij/B (implement with Big-M). **2-leg form (settled 2026-09-22, Section 13):** τ_ij and e_ij are the direct current-position→station leg; there is no separate origin/pickup leg (F5 in `REMEDIATION.md` Section 2, implemented as `station_gate` in `sim/formulas.py`).
- **C9 Big-M linearisation** of the bilinear rate × occupancy product in the SoC recurrence. Implemented in `solve_charge_schedule_milp_ccv` (`sim/milp.py`) with band-selection indicators z[i,t,l] — but **E8 in `REMEDIATION.md` is still open**: a slot uses the rate of the band it starts in for the whole slot, so with Δt=10min and B=90Wh a fast-band slot can add ~37% SoC, more than a band is wide, meaning CC-CV is not yet actually enforced within a slot. Not yet fixed.
- **C10 Charging continuity:** limits switching a pad on/off repeatedly across adjacent slots. Implemented — but **E9 in `REMEDIATION.md` is still open**: the dwell window is not truncated at the horizon end, so it can incorrectly forbid a charge that needs exactly the final slot. Not yet fixed.

C9 and C10 are implemented (`sim/milp.py::solve_charge_schedule_milp_ccv`) but have the two open issues (E8, E9) noted above.

### 4.6 Complexity

The problem is NP-hard: restricting to one station, uniform charging, no travel, and β = γ = 0 gives P||C_max (parallel-machine makespan), which is strongly NP-hard. The exact MILP is practical only up to about N = 15 drones. Hence a heuristic is needed.

---

## 5. The queue extension (our key modelling addition)

Constraint C1 enforces capacity but does not model the queue itself. The extension makes it explicit.

### 5.1 Gate vs cost (do not mix them)

**Reachability is a feasibility gate, evaluated first:**
$$F_i(t) = \{ j : S_i(t) - e_{ij}/B \ge \sigma \}$$
A station not in F_i is never scored. Folding reachability into a weighted cost could let distance outweigh safety.

**Distance and queue are costs, and both are measured in time**, so they combine without tuning weights:
$$J_{ij}(t) = \tau_{ij} + W_j(t+\tau_{ij}) + T^{chg}(S_i^{arr}, S_i^{tgt})$$
$$j^* = \arg\min_{j \in F_i} J_{ij}(t)$$

This minimises **time until mission-ready**, not distance.

### 5.2 Deterministic waiting time

Because the scheduler knows every reservation and target SoC, each pad's free time is computable exactly:
$$W_j(t) = \max\left(0,\ \min_{p \in pads(j)} free\_time(p) - t\right)$$
where free_time(p) accumulates the charge durations of reservations queued on pad p.

### 5.3 Asymmetry

A queued drone has landed (A6), so its SoC does not drop while it waits. **Reachability constrains safety; queueing constrains punctuality.** This justifies keeping them in separate parts of the model.

### 5.4 Reservation update (mandatory)

Drones are processed in priority order, and **each assignment updates W_j\* before the next drone is evaluated**. Without this, every drone picks the same station and performance collapses at high load.

---

## 6. Proposed heuristic: Energy-Aware Least-Slack-First with Pad Reservation

**Implemented 2026-09-22 (`sim/formulas.py`, `sim/ours_policy.py`) — this section now matches the actual code, which follows `REMEDIATION.md` Section 2's F1-F14 spec, not the earlier draft formulas.** The draft's `prio_i = w1/slack_i + w2/margin_i` had a units problem (adding a 1/minutes term to a 1/fraction term with no normalization) and is superseded by F11's normalized form below.

Priority score for each drone (F11, `combined_priority` in `sim/formulas.py`):
$$slack_i = d_i - (t + flight\_time_i) \quad \text{(F10, 2-leg: current position} \to \text{destination, no separate pickup leg)}$$
$$margin_i = S_i(t) - \sigma - \min_j e_{ij} / B$$
$$prio_i = w_1 \frac{T_{ref}}{\max(slack_i,\ \epsilon_t)} + w_2 \frac{\sigma}{\max(margin_i,\ \epsilon_s)}, \quad prio_i = +\infty \text{ if } slack_i \le 0 \text{ or } margin_i \le 0$$
where T_ref (a fixed time constant, computed not hardcoded — `time_to_reach_target_min(0, 1, B)`) and σ make the two terms comparable in scale instead of adding minutes to a raw fraction; the +∞ rule handles feasibility emergencies before the normal ranking. w1 = w2 = 1 (Section 13's Section 7 answer; a w1/w2 sweep is X8).

Station assignment cost (F8, `time_to_ready_cost`): $J_{ij}(t) = \tau_{ij} + W_j(t+\tau_{ij}) + T^{chg}(S_i^{arr}, S_i^{tgt})$, with $W_j$ computed exactly from each pad's reservation list (F7, `deterministic_wait`) — not estimated, since travel times and CC-CV charge durations are both deterministic once a reservation is made. Target SoC (F6, `target_soc`): $S_i^{tgt} = \min(1,\ \max(S_i^{req} + \sigma,\ S_{trigger} + 0.05))$, where $S_i^{req} = (e_{i \to d} + \min_{station} e_{d \to station})/B$ for the drone's next expected mission destination d (2-leg form).

```
at each decision epoch t:
    identify drones needing a charging decision
    rank them by combined_priority (F11, descending — infeasible cases first)
    for i in priority order:
        F_i <- station_gate(i)                       # F5, hard feasibility filter
        if F_i is empty: flag SAFETY_VIOLATION; continue
        j* <- argmin over F_i of time_to_ready_cost   # F8, uses F7's deterministic W_j
        S_target <- target_soc(...)                   # F6, partial-charging floor
        reserve pad at j*; UPDATE free_time[j*]        # F9, reservation update -- prevents stampede
        if use_jit: departure time <- jit_departure_time(...)   # F14, off by default
    assign missions by slack (F10, via _mission_slack)
    process departures for reserved drones whose dep_time arrived
    advance flights; transition waiting-for-pad drones to charging on arrival
    charge reserved/charging drones one tick (soc_after_charging)
    repeat at t+1
```

All 6 ablation flags from `REMEDIATION.md` Section 3 are implemented as boolean kwargs on `run_mission_sim_ours` (`sim/ours_policy.py`): `use_queue_term`, `use_reservation`, `use_priority`, `use_partial`, `use_jit`, `use_charge_time_term`. F9's reservation-update mechanism (stampede prevention) and F14's JIT departure timing both have dedicated tests (`tests/test_ours_policy.py`) confirming they do what they claim to — see checkpoint 4, Section 13.

Open questions: tuning w1/w2 beyond the current w1=w2=1 default (offline sweep is X8); whether an approximation ratio can be proved; station failures not handled.

---

## 7. Methodology principles (apply to every phase)

1. **Validation chain.** First reproduce the reference model exactly (Phase 1). Then show the simulator matches it under the same assumptions (Phase 2). Only then change assumptions.
2. **Change one assumption at a time.** Any difference in results must be attributable to exactly one change.
3. **Built-in sanity checks** (Section 8, Phase 3) must pass before any result is trusted.
4. **Common random numbers (CRN).** When comparing layouts or policies, run them on the **same** random arrival sequence for each seed. Differences then have far lower variance.
5. **Statistics.** At least 30 seeds per configuration for final results. Report means with 95% confidence intervals. Compare policies with paired tests (Wilcoxon signed-rank) on the same seeds.
6. **Time-weighted averages.** Queue length must be averaged over time (integral / horizon), never over events.
7. **Warm-up.** Discard the first 5–10% of simulated time before collecting statistics in final runs.
8. **Log everything from the first run.** Re-running large sweeps because a metric was forgotten is expensive.

---

## 8. Phase-by-phase plan with code specifications

**Phases 1-7's full pre-remediation narrative (exact commands, output, per-phase bug write-ups) has moved to `HISTORY.md`.** It is frozen 2026-09-21 status, before `REMEDIATION.md` existed. Current, active status — including everything that supersedes it — is in Section 13 below. Short current summary, cross-referenced to `HISTORY.md`:

- **Phase 1** (analytical replication) and **Phase 2** (simulator validation): done, unaffected by remediation. `HISTORY.md` has the full validation numbers.
- **Phase 3** (scheduler regimes R1-R3b): the mechanics (routing, event loop, sanity checks) are still in use, but its headline "crossover shift" conclusion is **superseded** by X1 (Section 13) — E1 found the original comparison wasn't like-for-like.
- **Phase 4** (mission layer, energy model, partial charging): core results still stand; `HISTORY.md` has the full write-up. The least-slack-first pad ordering built here is now the `pad_order='margin'` ablation, not the default (E5).
- **Phase 5** (MILP): built and tested, but its "0% gap" explanation is corrected by E10 (Section 13) — the v1 objective is constant across feasible schedules, so 0% gap shows correctness, not optimality. E8 (CC-CV slot-crossing) and E9 (dwell-window truncation) are still open.
- **Phase 6** (scale/statistics): the energy sign-reversal finding is **provisional** per E13 (Section 13) pending the X5 re-analysis; H5 is **untested**, not contradicted, per E12 (Section 13).
- **Phase 7** (figures/writing): a pre-remediation results-report PDF exists (`Phase1-6_Results_Report.pdf`) but is stale in the places listed above — do not cite it without cross-checking Section 13 first.

---

## 9. Expected results and hypotheses

**These are hypotheses to be tested, not predictions to be confirmed.** Never adjust code or parameters to make results match a hypothesis.

| ID | Hypothesis | Basis | **Status (2026-09-23, REMEDIATION.md Section 8 update)** |
|---|---|---|---|
| H1 | R2 equals R1 on average L and t | Kleinrock's conservation law (this is near-certain; failure means a bug) | **Confirmed**, queue-only model, `HISTORY.md`. Unaffected by remediation. |
| H2 | R2 beats R1 on deadline misses / window violations | Priority reallocates waiting to less urgent drones | **Refuted** in the queue-only model (R2 slightly *worse*, EDF's overload domino effect, `HISTORY.md`) and **not significant** in the mission-layer model (p=0.22-0.18, `HISTORY.md`). Not re-tested post-remediation. |
| H3 | In R3a, distributed charging's disadvantage shrinks sharply; the crossover may move a long way or vanish | Routing to shortest queue approaches pooled-queue performance | **Superseded finding, then a genuinely new one.** Pre-remediation "shift" claim (queue-only model) retracted after E1 (per-pad-vs-whole-hub) — corrected analysis showed R3a *loses* to pooling on mean wait throughout the practical load range (X1). **In the mission-layer model (X4, post pad-capacity fix): `ours` is the ONLY one of 4 primary policies (baseline, jsq, `ours`, B3) showing any layout crossover — baseline/jsq/B3 all show concentrated winning at every load tested.** Since `ours` and B3 differ by exactly one flag (`use_queue_term`), **the crossover is attributable specifically to F8's queue term** — the cleanest, most direct form this result has taken across the whole project. See "Headline results" below. |
| H4 | In R3b, travel distance partly restores the trade-off | Distributed pads are closer to drones than one central hub | **Confirmed, queue-only model** (X1, post-fix): R3b beats a fair concentrated-with-travel baseline from ρ≈1.0 up, loses below it — a real, 5-layout-robust crossover, tied to blocking-probability divergence. Not re-tested in the mission-layer model (R3b's queue-only geometry doesn't carry over to the depot/mission-layer instances). |
| H5 | Partial charging reduces makespan and misses most at high load | CC–CV tail makes the last 20% slow | **Tested directly for the first time in X5** (previously only total energy, not makespan/miss rate, had been measured — E12). Result: holds directionally for **baseline** at genuine stress points (`density_scarce`, `load_saturated`), is **essentially absent for `ours`** (no consistent benefit either direction), and **reverses** for baseline at a low-stress point (`fleet_12`) H5 doesn't even predict an effect for. **Restated (per direct instruction, replacing "mixed"): partial charging helps under stress for baseline; is neutral for `ours`, plausibly because `ours`'s own proactive scheduling (F5's lookahead trigger) already captures most of the benefit partial charging would otherwise add on top of a purely reactive baseline.** |
| H6 | The heuristic is within a few percent of the MILP at small scale | Design goal; must be measured | **Refuted for the CC-CV/mission MILP (v2); was never actually true for v1.** v1's historical "0% gap" (Phase 5, `HISTORY.md`) is now understood (E10, confirmed by X7's side-by-side run) to be a property of v1's degenerate constant pad-slot-count objective — not evidence of near-optimality. **X7 (real F12 objective, v2): mean gap 71.4% (non-binding-deadline instances) to 109.2% (tightened-deadline instances, see below) — not "a few percent" in either regime.** Mechanism identified directly (X7 write-up, Section 13): the MILP jointly co-optimizes drone-mission pairing, timing, and charge amount; the heuristic decides them sequentially and greedily, one epoch at a time, never revisiting a decision — a genuine, expected property of an online heuristic vs. an exact joint optimizer, not a defect. |

**All three Phase 3 outcomes are publishable:**
- Crossover shifts **right** → scheduling lets pads be consolidated further than queueing theory suggests.
- Crossover shifts **left** → scheduling and distributed layout complement each other.
- Crossover **disappears** → the analytical design guidance does not transfer to scheduled fleets (strongest result).

---

## 10. Baselines, metrics, figures

**Baselines:**
1. Threshold: charge to 100% whenever SoC < σ.
2. FCFS: first requester gets the first free pad.
3. Nearest-station greedy: same reachability gate, but **no W_j in the cost**. This is the ablation that isolates the value of the queue term. Do not drop it.
4. Proposed heuristic.
5. Exact MILP (small N only).

**Metrics:** average queue length, average waiting time, crossover ρ\*, makespan, deadline miss rate, optimality gap, station utilisation, mean realised queue delay, energy cost, scheduler runtime per epoch, safety violations (pass/fail, never a trade-off), reachability-gate binding rate, blocking probability.

**Figures:**

| # | Content | Phase |
|---|---|---|
| 1 | System model block diagram | — |
| 2 | Replication of reference crossover tables | 1 |
| 3 | Simulator vs analytical validation | 2 |
| 4 | Queue length vs ρ: reference vs scheduled | 3 |
| 5 | Waiting time vs ρ: reference vs scheduled | 3 |
| 6 | ρ\* shift across (n, m) with CIs for R1/R2/R3a/R3b | 3 (headline) |
| 7 | Ablation R1 vs R2 vs R3 | 3 |
| 8 | Deadline miss rate vs load, all policies | 4 |
| 9 | Partial vs full charging | 4 |
| 10 | Optimality gap vs fleet size | 5 |
| 11 | Scheduler runtime vs fleet size | 6 |

---

## 11. Coding conventions

- **Language:** Python 3.10+. Libraries: numpy, scipy, pandas, matplotlib; pyomo or pulp for the MILP; highspy or CBC as default solver.
- **Structure:**
```
project/
  phase1_baseline.py        # existing, validated
  sim/
    core.py                 # event loop, shared data structures
    energy.py               # flight energy, SoC, CC-CV curve
    scheduler.py            # priority, gate, cost, reservation
    policies.py             # FCFS, threshold, nearest-greedy, proposed
    milp.py                 # Pyomo/PuLP model
    metrics.py              # all metric computations
    stats.py                # CIs, bootstrap, paired tests, crossover fit
  experiments/
    phase3_regimes.py
    phase4_missions.py
    phase5_milp_gap.py
    phase6_scale.py
  tests/
    test_phase1.py          # tables 2 and 3 within 1e-3
    test_phase2.py          # sim vs analytic
    test_phase3_sanity.py   # slack-zero and conservation checks
  results/                  # raw CSV per run, never overwritten
  figures/
```
- Every experiment takes an explicit `seed` and writes raw per-run results to CSV (one row per run, all parameters included) before any aggregation.
- Configuration via a dataclass or YAML; no hard-coded magic numbers inside functions.
- Units in variable names or docstrings (Wh, W, s, m).
- Every phase has a test file; tests must pass before experiments run.
- Plots are generated from saved CSVs, never from in-memory results only.

---

## 12. Known pitfalls

- Concentrated capacity is n·m, not m.
- Division by zero at ρ = 1; use the limit forms.
- Waiting time has 1/λ factored out in the reference paper.
- Queue length must be time-weighted.
- Plain bisection on noisy simulation output is unreliable; use grid + fit + bootstrap.
- Without the reservation update, the greedy station choice collapses.
- R3 changes two things unless split into R3a/R3b.
- Priority rules show no benefit on averages (by theory); measure per-drone outcomes.
- If the reachability gate never binds, scenarios are too easy; log its binding rate.
- In MILP: oversized Big-M makes solving very slow; symmetry slows it further.
- L_d (Eq. 11) is one queue's length, with no n dependence; comparing it directly to L_c (whole hub) is not like-for-like. Use per-drone wait t as primary, or n·L_d for a genuine total-queue comparison (Section 13).
- `bisect()` on a bracket that doesn't actually contain a root converges silently to a wrong number with no error — always sanity-check *where* the crossover actually is (scan first) before trusting a bracket carried over from a different metric or config. `phase1_baseline.bisect` now raises `ValueError` on a same-sign bracket, but downstream code that assumes a specific window can still silently ask it the wrong question.
- At ρ<1 (low/moderate load), blocking is near zero for every regime tested (R1, R3a, R3b) — differences there reflect genuine queueing/routing behaviour. At ρ≥1, blocking probability diverges sharply between regimes and drives most of the reported gap; always report blocking probability alongside any ρ≥1 comparison, or the result is uninterpretable (Section 13, X1).

---

## 13. Current status and open decisions

**Active work (2026-09-22): follow `REMEDIATION.md`.** A review found the Phase 3-6 crossover metric was not like-for-like (E1: per-pad L_d compared against whole-hub L_c — at ρ=0.8,n=5,m=7 this reverses which layout looks better, verified numerically) and that the project's own proposed method (deterministic waiting time, reservation update, combined priority, time-to-ready cost) was never actually implemented — only reference-paper formulas, JSQ, and a partial-charging policy were. `REMEDIATION.md` is the authoritative spec for the fixes (E1-E13) and the real method (F1-F14) going forward. Results below marked superseded as fixes land.

**Section 7 open decisions, answered 2026-09-22:**
1. Flight energy: keep flat-rate κ=0.01 Wh/m (validated); add the `ENERGY_MODEL="flat"|"power"` config switch so F1/F2 (power model) is ready once real β0-β3 exist. E_to=E_land=0, logged as an assumption.
2. JIT dispatch (F14): **off by default** in `ours`, but run `ours+JIT` as a full named variant (not just an ablation toggle) in X1, X3, and X4. **Superseded 2026-09-22 for the X1 part only** (see the decision below, Section 9 step 3 log): X1 is the queue-only model, where F14 isn't principled (random service times, no true reservation to be JIT about). `ours+JIT` still runs in X3 and X4 as originally answered, where F7's deterministic waiting time genuinely holds.
3. Objective (F12): α=β=γ=1 applied to **normalized** terms: C_max/horizon_length; energy_cost/(flat_price × total_mission_energy); total_tardiness/(n_missions × mean_mission_duration). Flat tariff for all main experiments and the MILP gap; time-of-use only in X8, with the horizon shifted so it actually covers the 17:00-21:00 peak (fixes the earlier flagged issue where the Phase 6 tariff experiment's horizon never reached peak hours).
4. Priority weights (F11): w1=w2=1, to be swept later in X8.
5. **Origin-leg modelling decision (2026-09-22):** missions have a single work site (`destination`), no separate pickup point (`origin`) distinct from the drone's current position — matches the code as built (`Mission` in `sim/models.py` has no `origin` field) and is now the spec, not a gap. `REMEDIATION.md`'s F5 (reachability gate), F6 (target SoC), F10 (slack) updated to the 2-leg form (current position → destination [→ station], not current → origin → destination [→ station]). Stated in the paper as a simplification: a mission is "go to `destination` and perform the task there," not "go to `origin`, pick up, deliver to `destination`." If a genuine pickup leg is needed later, `origin` would need to be added to `Mission` and F5/F6/F10 extended back to three legs.

Starting test state before any remediation code changes (2026-09-22): `pytest -q` → 40 passed.

**Checkpoint 1 (Section 9 step 2 — E3, E5, E6, E7), done, 45 passed:**
- **E1 confirmed** (not a code fix — a metric-choice finding): verified numerically at ρ=0.8,n=5,m=7 that L_d<L_c (per-pad, says distributed wins) but n·L_d>L_c (whole-system, says concentrated wins) — opposite conclusions. Also confirmed t_d = n·L_d/(1-P_blocking) exactly, so wait time is already like-for-like. Test: `test_fixes.py::test_E1_per_pad_vs_whole_hub_is_not_like_for_like`.
- **E3 fixed**: `sim/scheduler.py` JSQ/JSQ+travel routing now uses in-system count (not waiting-only), with ties broken on a separate deterministic RNG stream (`seed*1_000_003+7919`) that never touches the main arrival/service/slack draws — so every previously-validated result that doesn't tie-break (R1 vs analytics, conservation check) remains bit-for-bit reproducible.
- **E5 fixed**: `sim/mission_sim.py` gained a `pad_order` parameter, decoupled from `order`. Margin-based pad-queue service is now `pad_order='margin'`, an explicit opt-in ablation — no longer the implied behavior of `order='priority'`. Default is FCFS at the pad (reservation-order service, F7-F9, awaits the Section 3/4 build).
- **E6 checked, not modified**: the exact counter-example in REMEDIATION.md (`test_E6_reachability_gate_already_refuses_the_stranding_case`) already passes on unmodified code — `_reachable_with_return` (added earlier while fixing a different bug: 1410 safety violations from stranded drones) already holds σ on arrival at the eventual station, not just the mission destination. No fix applied; reported as verified-already-correct rather than "fixed" for appearances.
- **E7 fixed**: mission ranking now uses `_mission_slack` (deadline minus now-plus-flight-time via the nearest available drone) instead of raw `deadline - t`. Test confirms a later-deadline-but-much-longer-flight mission ranks strictly more urgent than raw deadline order alone would produce.

**E4 completed** (2026-09-22), the remaining piece of checkpoint 1 (Section 9 step 2):
- **E4(a) fixed**: `jsq_travel`'s cost was combining real-world travel time in seconds (up to ~188s across the 2000m area) directly with `n_in_system/mu` (O(1-10) scale) — travel dominated the routing decision at every load, not just low load. Now converted to minutes (`/60`), max ~3.14 min, a comparable scale to the queue term.
- **E4(b)** already covered by the E3 fix (in-system count, not waiting-only) — applied to `jsq_travel` too.
- **E4(c) fixed**: routing was instant — a request decided its station and joined the queue in the same tick, with no travel delay at all. Restructured `sim/scheduler.py`'s event loop to a genuine 3-event-type structure (request → pad-arrival scheduled at t+travel_time → departure), so a routed request now actually takes travel_time to occupy a slot, exactly like a real flying drone. Verified: for `fixed_split`/`jsq` (travel=0), the new `total_delay` metric equals `wait` exactly (bit-identical), confirming zero behavior change for R1/R2/R3a. For `jsq_travel`, `total_delay` (includes travel) is now reported separately from `wait` (on-pad only, still the metric validated against Phase 1/2 analytics) — REMEDIATION.md's accounting rule (moving waiting off the pad must never make it disappear from the metrics).
- **E4(d) built**: new `simulate_concentrated_with_travel` (single hub, n_servers parallel pads, capacity n·m, same event-scheduled-arrival mechanism) — cross-checked against the validated M/M/n/nm analytics with travel disabled (huge speed) and matched within 2%, same order as Phase 2's own validation margin. `centroid()` helper places the hub at the distributed layout's station centroid, so R3b and the concentrated baseline now share coherent geometry.

**First fair R3b-vs-concentrated comparison** (n=5, m=7, seed=1, horizon=20000, both paying real travel cost): ρ=0.6 → concentrated wins (L=0.339 vs R3b's 0.475); ρ=0.8 → R3b wins (L=1.170 vs 2.278); ρ=1.0/1.2 → R3b wins decisively (2.5 vs 14.1, 3.6 vs 25.1). **A real crossover still exists, located close to the original travel-free analytical value (~0.7)** — but this is a single seed at one station layout, not yet the ≥5-layout, 30-seed rigor X1 will require. The earlier claimed "R3b worse than R1 at low ρ due to travel-dominated routing" finding is now understood to have been substantially a units artifact, not a real property of travel-aware routing — **superseded**.

**Checkpoint 2 (Section 9 step 2) complete: E3, E4, E5, E6, E7 all done, re-verified directly from code on 2026-09-22 (not from docs):**
- E5: `pad_order='fcfs'` is the function default (`sim/mission_sim.py` line 87); margin-ordering only fires on explicit `pad_order='margin'` (line 266); no remaining path where `order='priority'` implies margin ordering.
- E6: the final check in `_reachable_with_return`, `(soc_after_arrival - best_return) >= SIGMA`, algebraically requires SoC at arrival at the eventual **station** (destination leg + return leg both subtracted) to hold σ, not just at the mission destination.

`pytest -q` → 49 passed.

**Checkpoint 3 (Section 9 step 3) in progress: fix E1, E2; run X1, X2.**

**E2 fixed**: `sim/stats.py::estimate_crossover_ci` gained a cubic-spline root-finding method (default), replacing plain linear interpolation between the two bracketing grid points. Bias measured directly on exact analytic inputs (no simulation noise at all), before and after:

| (n,m) | grid points | linear bias | spline bias |
|---|---|---|---|
| (5,7) | 6 | 0.000173 | 0.000007 |
| (4,6) | 5 | 0.001812 | 0.000041 |
| (10,9) | 5 | 0.005799 | 0.000840 |

All three now under E2's required 0.001 threshold (n=10,m=9 improved ~7x). This confirms the earlier "simulated CI misses the analytic crossover" observation at (4,6) and (10,9) was genuinely an interpolation-bias artifact, not simulation noise as originally assumed. Test: `test_stats.py::test_crossover_ci_bias_on_analytic_inputs_meets_e2_threshold`.

**E1 fix, real bug caught mid-run, not silently accepted:** `experiments/x1_corrected_crossover.py` reused the L-crossover's rho grid (bracketing ~0.70-0.83, Table 2) for the primary t-crossover metric too. Table 3 shows the wait-time crossover sits at a completely different location (~1.00-1.02, close to ρ=1) — the old grid never reached it, so `estimate_crossover_ci` correctly returned "no sign change found" (None) at every config, not a wrong number but a diagnostic that the experiment design was broken. Caught by reading the actual run output rather than assuming a background job's eventual CSV would be usable. Fixed with `experiments/x1_t_crossover.py`, using per-config grids tailored to each (n,m)'s actual Table 3 crossover location (n=4,m=6 near 1.019; n=5,m=7 near 1.010; n=10,m=9 near 1.003 — very close to 1, needing a tight grid). Scope: 15 seeds, horizon=30,000 (not 30/50,000 — rho≈1 is the most expensive region to simulate; full rigor would take hours), a first real pass at the primary metric, not final numbers.

**X1 results, complete (2026-09-22), corrected 2026-09-22 after user review found two more real bugs (below the R3a/R3b bug list):**

*Primary metric — per-drone wait-time crossover (R1, `experiments/x1_t_crossover.py`, 15 seeds, horizon=30,000, results at `results/x1_t_crossover_20260922_173448.csv`):*

| (n,m) | R1 t-crossover ρ* (95% CI) | Table 3 analytic | CI contains the true value? |
|---|---|---|---|
| (4,6) | 1.01760 [1.01597, 1.01899] | **1.01919** | **No — miss** |
| (5,7) | 1.00972 [1.00877, 1.01064] | 1.01041 | Yes |
| (10,9) | 1.00258 [1.00236, 1.00275] | **1.002478** | Yes |

**Correction (2026-09-22): the (10,9) row above was originally reported as 1.00321, which is `TABLE3[10][m=8]`, the wrong column of the right row — the correct m=9 value is 1.002478466796875.** Against the correct value, the (10,9) CI [1.00236, 1.00275] already contained the truth at the original horizon=30,000 — it was never actually a miss. **The real miss is (4,6)**: 1.01919 sits just above the CI's upper bound (1.01899). Regression test added: `test_fixes.py::test_table3_lookup_n10_m9_is_the_m9_column_not_m8`.

Re-ran (4,6) at horizon=200,000 (vs 30,000) with 15% warm-up (vs 10%) — the same treatment originally (and, per the correction above, unnecessarily) applied to (10,9) — `experiments/x1_horizon_bias_check_46.py`, results at `results/x1_horizon_bias_check_46_20260922_192025.csv`, 566.4s: **R1 t-crossover ρ\* = 1.01956, 95% CI [1.01875, 1.02050], true analytic crossover 1.019210 (Table 3: 1.019189) — the CI now contains the true value.** This matches the same finite-horizon-bias signature already confirmed for (10,9): ρ≈1 is a heavy-traffic regime where queues mix slowly, and horizon=30,000 (chosen so the original 3-config sweep finished in ~45min rather than several hours) was too short to reach steady state at this specific load. With this fix, **all three (n,m) configs' CIs now contain their true analytic crossover** — no primary-metric miss remains.

**R3a's t-crossover and L-crossover are both `None` at every config** (`experiments/x1_corrected_crossover.py`, results at `results/x1_corrected_crossover_20260922_171244.csv`, 30 seeds, horizon=50,000) — its advantage over concentrated on both metrics is now strong enough (post-E3 fix) to persist across the entire tested ρ range without crossing back, not just a modest leftward shift as reported pre-remediation. This is a materially stronger finding than the earlier (buggy-routing) "shift of ~0.11-0.13" result, which is now superseded. **[This "None" finding is itself corrected further down — it was misread as an R3a win; R3a actually loses to concentrated throughout, see the reopened checkpoint-3 log below.]**

*Secondary metrics (R1 only, "replication of the reference metric," per E1):*

| (n,m) | L-crossover (replication only) | Table 2 analytic | Total-queue crossover (n·L_d vs L_c, analytic) |
|---|---|---|---|
| (4,6) | 0.7069 | 0.70752 | **0.9838** |
| (5,7) | 0.7504 | 0.75049 | **0.9889** |
| (10,9) | 0.8262 | 0.82529 | **0.9956** |

**Correction (2026-09-22): the total-queue crossover column above was originally reported as 0.750/0.800/0.900 — wrong, by a real bug found by the user.** `total_queue_crossover()` (`experiments/x1_corrected_crossover.py`) passed `bisect()` the same bracket used for that config's per-drone-wait rho_grid (e.g. (0.55, 0.80) for (5,7)) on the unexamined assumption that the total-queue crossover sits near the same location — it doesn't. A fine scan (`n·L_d − L_c` from ρ=0.50 to 1.50 in steps of 0.01) shows all three configs cross between ρ=0.95 and 1.00, so the old bracket never contained the root and `bisect` (before it validated its bracket — see below) silently returned a number anchored to the wrong window. Fixed by scanning for the sign change first, then bisecting within the bracket that's actually found (`tol=1e-9`): **(4,6): 0.983783, (5,7): 0.988904, (10,9): 0.995594**. Regression test: `test_fixes.py::test_total_queue_crossover_bracket_actually_contains_a_root`. `phase1_baseline.bisect` itself now raises `ValueError` if the given bracket's endpoints don't have opposite signs, instead of silently converging inside a bracket with no real root — this exact failure mode is what produced the wrong 0.750/0.800/0.900 numbers, so the fix is at the tool level, not just this one call site.

**Note:** the corrected total-queue crossover (≈0.98-1.00) sits much closer to Table 3's own waiting-time crossover (≈1.00-1.02) than to Table 2's per-queue crossover (≈0.71-0.83) — see the new note added to Section 3.3, which uses this as a plausible explanation for why Tables 2 and 3 disagree in the reference paper itself.

**R3b vs. fair concentrated-with-travel baseline, ≥5 layouts** (`experiments/x1_r3b_layouts.py`, 10 seeds, horizon=20,000, results at `results/x1_r3b_layouts_20260922_171631.csv`, n=5,m=7): **the crossover location is robust across all 5 random station layouts** — concentrated wins only at ρ=0.6 (R3b L≈0.44-0.56 vs concentrated≈0.34-0.35), R3b wins decisively from ρ=0.8 up (e.g. at ρ=1.0: R3b≈2.44-2.52 vs concentrated≈13.8-14.0, consistently across every layout). This was a real risk (the earlier single-layout R3b finding had already been shown to depend on the specific layout's geometry for a different reason — the pre-E4-fix units bug), and it held up. **This L-based result was later superseded by the corrected `total_delay`-based metric below — kept here only as the first (partial-metric) pass.**

**Checkpoint 3 initially reported complete, then re-opened by user review — two more real issues caught, 2026-09-22:**

1. **The R3a "None" finding was mis-interpreted, not a bug in the simulation.** A pooled M/M/n queue is provably at least as good as any routing to n separate single-server queues on mean wait (any waiting customer in a pooled system can be served by whichever server frees next; distributed routing locks a customer to its assigned station's single server). A sanity test at ρ=0.5 (negligible blocking) **passes**: R3a's wait (0.2725) is correctly higher (worse) than the concentrated analytic (0.1304) — now a permanent regression test (`test_pooling_bound_r3a_cannot_beat_concentrated_wait_at_negligible_blocking`).

   **A full ρ=0.2-1.6 diagnostic grid (n=5,m=7, 15 seeds, horizon=30,000, `results/x1_r3a_diagnostic_20260922_180915.csv`) resolved it completely**: R3a **loses** to concentrated at every single point from ρ=0.2 through ρ=1.1 (e.g. ρ=0.6: t=0.644 vs t_c=0.354; ρ=1.0: t=15.353 vs t_c=14.303; ρ=1.1: t=24.014 vs t_c=23.706) — exactly matching the pooling-superiority theorem throughout the practical load range. Only at ρ=1.2-1.5 (deep overload, block_frac 17-33%) do R3a and concentrated become statistically indistinguishable (e.g. ρ=1.2: 30.092 vs 30.107, a 0.05% difference) — noise near convergence in the heavy-overload regime, not a real win, plausibly because pooling's advantage shrinks toward zero once both systems are dominated by similar deep-blocking dynamics.

   **The earlier "None" result (no crossing found in the originally-tested, narrower ranges) was actually correct all along** — R3a never beats concentrated in those windows, so "no sign change" was the right answer. **The error was mine, in interpretation**: I reported "its advantage over concentrated persists across the entire tested range," assuming without checking that "None" meant R3a was winning throughout — the literal opposite of what the data shows. **Corrected finding, superseding both the pre-remediation "shift left" claim and my own immediately-prior mis-statement: smart JSQ routing (R3a) does NOT outperform pooling (concentrated) on mean wait time across the practical load range (ρ=0.2-1.1) — it is consistently worse, as queueing theory predicts, converging to roughly equal only under deep overload.** This substantially revises the Phase 3 "routing shifts the crossover" narrative — that narrative was built on the L-metric before E1's fix, and does not survive the corrected wait-time metric.
2. **The R3b vs. concentrated-with-travel comparison had TWO real bugs, found in sequence.** (a) `simulate_regime`'s `L` (used for R3b) is per-station average (divided by n_stations); `simulate_concentrated_with_travel`'s `L` is the whole-hub total (not divided). The "R3b wins decisively" claim (2.4-2.5 vs 13.8-14.0) was comparing a per-pad average against a whole-system total — the identical category error E1 was supposed to have fixed, recommitted in a new place. Caught by the user asking "which metric is this in?" before accepting the result. (b) The first re-fix then used `wait` (on-pad delay ONLY, explicitly excludes travel per the module's own docstring) as the primary comparison metric instead of `total_delay` (which includes travel, matching E4(c)'s own accounting rule — "a drone's charging delay is always measured as charge_start - charge_request_time, regardless of where it waited"). Worse, `total_delay` is NOT rescaled by `lam_total` in the return value (only `wait` is), so multiplying `wait` by `lam_total` and comparing it directly against unrescaled `total_delay` silently mixed two different scalings. Caught by checking why R3b's reported wait (2.36, rescaled) looked implausibly high for ρ=0.6 with near-zero blocking — printing both fields directly showed the mismatch. **A genuine, non-bug finding surfaced along the way**: R3b's own on-pad wait (0.787, unscaled) is ~3.7x higher than pure-JSQ's (R3a) at the same ρ=0.6 — travel-cost-aware routing creates real on-pad congestion at low load, because the travel term in the routing cost dominates the near-zero queue term there, sometimes sending a drone to a closer-but-busier station over a farther-but-empty one. **Re-run with the corrected `total_delay * lam_total` metric, complete** (`experiments/x1_r3b_corrected_metric.py`, 10 seeds, horizon=20,000, all 5 layouts, results at `results/x1_r3b_corrected_metric_20260922_182214.csv` — corrected here from an earlier CSV-filename typo, `...182302.csv`, which was never a real file):

| ρ | R3b total_delay | Concentrated total_delay | R3b total queue | Concentrated total queue | block_r3b | block_conc | Winner (both metrics) |
|---|---|---|---|---|---|---|---|
| 0.6 | 4.4-5.9 | 2.9-3.7 | 2.2-2.8 | 0.34-0.35 | 0.08% | 0.00% | **Concentrated** |
| 0.8 | 9.4-11.1 | 5.6-6.7 | 5.9-6.6 | 2.18-2.25 | 1.21% | 0.01% | **Concentrated** |
| 1.0 | 18.0-18.8 | 18.6-19.8 | 12.2-12.6 | 13.7-14.0 | 7.31% | 2.97% | **R3b** |
| 1.2 | 27.4-27.7 | 35.0-36.8 | 17.0-18.3 | 24.9-25.7 | 18.37% | 16.60% | **R3b** |

**Consistent across all 5 layouts on both metrics — this is a real, properly-verified crossover, unlike R3a's.** Concentrated (pooling, even paying its own travel cost) wins decisively at low load; R3b (distributed + travel-aware routing) wins decisively from ρ=1.0 up. The qualitative direction of the original (buggy) finding turns out to have been right for R3b specifically, even though the reasoning and exact numbers behind it were wrong twice over — worth stating plainly rather than treating as vindication, since it could easily have gone the other way (as R3a's case shows).
3. **Confirmed: the R1 t-crossover CI misses were genuine finite-horizon bias, not estimator variance.** Re-ran n=10,m=9 (the worse miss, crossover at ρ≈1.003, the most heavy-traffic-adjacent case) with horizon=200,000 (vs 30,000) and 15% warm-up (vs 10%), `results/x1_horizon_bias_check_20260922_182158.csv`: the gap to the true analytic crossover shrank from +0.000106 (horizon=30,000) to **-0.000010** (horizon=200,000) — a ~10x reduction, with the new 95% CI [1.0024099, 1.0025320] now containing the true value (1.002476) directly. This is the expected signature of finite-horizon bias (ρ≈1 is a heavy-traffic regime where queues mix slowly, needing a much longer horizon to reach steady state) and rules out the estimator itself as the cause — E2's spline fix is not implicated. **[Correction, item 4 below: this (10,9) re-run turned out not to have been necessary — see the table-transcription bug found in a later review round. The finite-horizon-bias mechanism it confirmed was still real, and is what (4,6)'s later re-run, item 4 below, actually needed.]** **Correction to Section 8's Phase 3 entry (now `HISTORY.md`)**: the earlier explanation ("a linear-interpolation-resolution artifact from the coarser 5-point grid") was wrong; the real cause is finite-horizon bias at the shorter (30,000) horizon used for the primary-metric run, not grid coarseness (which E2 already fixed for the L-crossover work).

**R3b, additional detail (2026-09-22): paired per-layout 95% CIs, R3b − Concentrated total_delay, at ρ=1.0** (paired on seed within each layout, 10 seeds/layout, from the same CSV):

| layout_seed | mean(R3b − Conc) | 95% CI | Significant? |
|---|---|---|---|
| 0 | −0.518 | [−0.684, −0.351] | R3b lower (better) |
| 1 | −0.402 | [−0.822, **+0.017**] | **Overlaps zero — not significant at this layout** |
| 2 | −0.729 | [−0.966, −0.491] | R3b lower (better) |
| 3 | −0.806 | [−1.059, −0.553] | R3b lower (better) |
| 4 | −0.972 | [−1.223, −0.720] | R3b lower (better) |

4 of 5 layouts show R3b significantly lower total_delay at ρ=1.0; layout 1's CI includes zero, so that one layout alone does not reach significance at 10 seeds — consistent with (not contradicting) the pooled 5-layout result above, since the pooled comparison has more power than any single layout.

**Explicit statement (2026-09-22), tying R1, R3a and R3b together:** at ρ<1, blocking is negligible for every regime tested (≤1.2% for R3a and R3b, ≤0.01% for concentrated — see the blocking table above and the ρ=0.9 row two paragraphs up), and **the concentrated hub wins on every fair (like-for-like, total-system) metric checked for R1, R3a, and R3b alike** — this is a genuine queueing-theory result (pooling beats splitting when there's little rejection to trade against), not a blocking artifact. At ρ≥1, blocking probability diverges sharply between regimes (e.g. at ρ=1.0: R3b 7.3% vs concentrated 3.0%; at ρ=1.2: R3a's own diagnostic shows 16.6% vs the analytic 16.7%) and **most of the reported ρ≥1 gap is a blocking-probability effect**, not purely a queueing-discipline effect — a regime that blocks more effectively serves less total demand, which can lower its own average delay among admitted drones without doing better "for the fleet" in any welfare sense. The ρ≥1 numbers are real and reproducible, but should be read as "which regime rejects and delays admitted drones differently under overload," not as an unqualified performance ranking.

**Limitation, recorded rather than chased with more queue-only runs (2026-09-22):** this queue-only model uses 1/μ = 1 minute mean service time, while travel times in R3b are up to ~3 minutes (comparable to or longer than a service time) and real CC-CV charging sessions (Phase 4/X3/X4 scale) run tens of minutes. The queue-only R3b result above is therefore informative about routing-with-travel *in a regime where travel and service are comparable in size*, not about the actual mission-layer timescale, where a charge session dwarfs any travel leg and the balance between the two could look qualitatively different. **No further R3b experiments are planned in the queue-only model** — the travel-vs-charging-time question moves to X4 (the CC-CV mission-layer experiment, checkpoint 5), where both are measured on their real scale together.

**A second round of review (2026-09-22, after the above was reported as complete) caught two more real bugs, both in the write-up/analysis layer, not the simulation engines:**

4. **The (10,9) Table 3 value was transcribed from the wrong column** (1.00321, `TABLE3[10][m=8]`, instead of 1.002478, `TABLE3[10][m=9]`) — see the primary-metric table above. This flipped which config actually missed its CI: (10,9) was never a real miss; (4,6) was, and has now been re-run at horizon=200,000 and closes the same way (10,9) did originally.
5. **The total-queue crossover (n·L_d vs L_c) values were wrong** (0.750/0.800/0.900, reported as if analytic) because the bisection bracket was silently reused from a different metric's rho_grid and never contained the real root (~0.98-1.00 for all three configs) — see the secondary-metrics table above. `phase1_baseline.bisect` now validates its bracket instead of silently returning a wrong answer.

**Checkpoint 3 (Section 9 step 3), now genuinely complete, 2026-09-22 (revised).** Summary of what changed under review, across both rounds: R3a shows no real advantage over concentrated anywhere in the practical load range (corrected from a misinterpreted "None" result); R3b's advantage from ρ=1.0 up is confirmed real and robust across 5 layouts and across paired per-layout CIs, but only after fixing two metric bugs (per-pad-vs-whole-hub, then wait-vs-total_delay) — and is now explicitly tied to blocking-probability divergence at ρ≥1, with a recorded timescale limitation (queue-only model's 1/μ vs travel vs real charging durations); the R1 t-crossover CI misses are confirmed finite-horizon bias, closed by a longer horizon at the *correct* config (4,6), once a table transcription bug was caught; and a bracket bug that produced wrong total-queue-crossover numbers is fixed with a general safety check in `bisect()` itself, not just a one-off patch. None of these five issues were bugs in the underlying `simulate_regime`/`simulate_concentrated_with_travel` engines, which have passed every direct check throughout; all five were in analysis/reporting code or in a table lookup. `pytest -q` → 67 passed (2 new regression tests added for issues 4 and 5). Not yet re-run at full 30-seed/original-horizon rigor for all three (n,m) configs on every metric — the above used reduced-scope diagnostic and targeted re-runs to resolve the specific questions raised; a full-rigor final pass would still be needed before these numbers are final-report quality.

**R3a's routing changed under E3's fix** (waiting-count → in-system-count), so its earlier-saved crossover CSVs are stale and are being regenerated by this run; R1's routing (`fixed_split`) was untouched by E3, so its numbers are expected to match the earlier run closely (same computation, just now also recording `wait` alongside `L`).

### Checkpoint 4 (Section 9 step 4): F1-F14 and the full heuristic

**First pass (2026-09-22), reported complete, was NOT actually done to spec.** `sim/formulas.py` (F4-F11, F14) was genuinely built and tested. But the heuristic itself was built as a **separate, parallel engine** (`sim/ours_policy.py::run_mission_sim_ours`), duplicating `sim/mission_sim.py`'s flight/mission bookkeeping — not, as REMEDIATION.md Section 3 explicitly specifies, "a policy `policy='ours'` in the Phase 4 mission simulator." F12 (the objective) was never implemented at all. `tests/test_prediction.py` tested the standalone engine, not "the Phase 4 simulator" as Section 5 requires. `tests/test_regression.py` didn't exist. Caught when the user asked to confirm `policy='ours'` and the Section 5 tests directly from the code rather than the prior report.

**Real checkpoint 4, complete, 2026-09-22:**

1. **`sim/formulas.py`**: unchanged from the first pass — F4-F11, F14 (pure functions), plus **F12 added** (`objective_F12`): Z and its three normalized terms (C_max/horizon; energy_cost/(flat_price×total_mission_energy); tardiness/(n_missions×mean_mission_duration)), computed for every policy run, returned as `f12_Z`/`f12_cmax_term`/`f12_energy_term`/`f12_tardy_term`. Two assumptions made explicit in the code and here: (a) `total_mission_energy` is **mission-flight energy only**, excluding charger-trip legs — tracked by a separate accumulator in `run_mission_sim` that only adds energy while `state == "FLYING_MISSION"`; (b) `mean_mission_duration` uses `deadline_window_min` (a fixed, run-independent constant, same for every mission in this model) rather than the empirical mean completion time, since the latter would let a slower policy shrink its own tardiness term.
2. **`sim/mission_sim.py`**: `run_mission_sim` gained a `policy: str = "baseline"` parameter, replacing the separate `sim/ours_policy.py` (deleted after the equivalence check below). Three policies, all sharing one function, one RNG-draw sequence (mission/UAV generation identical regardless of policy, for CRN validity across policy comparisons at the same seed):
   - **`policy="baseline"`** (default): the original threshold-triggered, nearest-station dispatch, governed by `charge_policy`/`pad_order` exactly as before. **Per REMEDIATION.md Section 6, this one configuration realises BOTH B1 (Threshold: charge to 100% when S≤S_trigger, nearest station) and B2 (FCFS: first requester gets first free pad, nearest station) simultaneously** — the model has no axis that separates "threshold-triggered full charge" from "FCFS pad admission"; both are true of the same existing mechanism, not two different code paths. Stated plainly rather than inventing an artificial distinction.
   - **`policy="jsq"`** (new, B4): route to the reachable station with fewest drones in system (pads_busy+queue length), ties broken on a separate RNG stream (`seed*1_000_003+7919`, same pattern as `sim/scheduler.py`'s E3 fix), no reservation/free-time projection ("no reservation" per spec — live counts only, stampede-vulnerable by design), always full charge target, FCFS at the pad.
   - **`policy="ours"`**: the full heuristic (F1-F11+F14, all six ablation flags), ported from the deleted `sim/ours_policy.py`. **B3 (nearest-time greedy) is this policy with `use_queue_term=False`, not a separate code path** — REMEDIATION.md's own Section 6 table defines it that way.
   - **Invalid combinations now raise `ValueError`** instead of being silently ignored: `charge_policy`/`pad_order` only apply to `policy="baseline"`; `w1`/`w2`/the six ablation flags only apply to `policy="ours"`. Test: `test_ours_policy.py::test_invalid_combo_charge_policy_with_ours_raises`.
   - **Drain period added** (`drain_cap_min: float = 0.0`, default off): after the horizon, if any released mission is still incomplete and `drain_cap_min > 0`, keep advancing ticks (no new releases) for up to that many extra minutes so in-flight/in-queue work can finish, instead of cutting off mid-mission. `unfinished_at_cap` in the return dict reports how many released missions were still incomplete when the loop stopped, whether or not draining was used. Default `0.0` preserves the exact pre-checkpoint-4 loop length for every policy (needed for the exact-reproduction requirement below).
3. **Exact backward-compatibility verified, not assumed.** Before touching `sim/mission_sim.py`, captured golden output from the unmodified code on 3 fixed configs covering every pre-existing parameter (`charge_policy` full/adaptive, `order` fcfs/priority, `pad_order` fcfs/margin, `tariff` flat/tou). After the refactor, `policy="baseline"` reproduces all 10 checked fields **bit-for-bit** on all 3 configs — now a permanent test, `tests/test_regression.py::test_policy_baseline_reproduces_pre_checkpoint4_outputs_exactly`. Same procedure for the merge: captured golden output from the standalone `run_mission_sim_ours` on 3 fixed configs (including `use_jit=True` and `use_queue_term=False`) **before** deleting it, then confirmed `run_mission_sim(policy="ours", ...)` matches bit-for-bit on all 3 — only then was `sim/ours_policy.py` deleted.
4. **All Section 5 tests pass, now actually testing "the Phase 4 simulator":**
   - `tests/test_formulas.py` (14 tests: the original 8 F4-F11 formula tests, plus 3 new F12 tests — normalized-terms arithmetic on hand-picked numbers including the zero-denominator edge case; the mission-energy-excludes-charger-trips rule, verified two ways (a charger-trip-only run where `mission_flight_energy_wh` must be exactly `0.0`, and a mission-only run where it's independently recomputed by replicating the exact RNG draws `run_mission_sim` uses internally); the drain-period rule, verified by cutting a 2-mission run off mid-way through the second mission and checking `unfinished_at_cap` drops from 1 to 0 once a generous `drain_cap_min` is given).
   - `tests/test_ours_policy.py` (5 tests: safety/determinism, all-ablations-run-safely, the new invalid-combination test, **F9's stampede test**, **F14's JIT test** — all four repointed to `run_mission_sim(policy="ours", ...)`).
   - `tests/test_prediction.py` (2 tests, repointed to `run_mission_sim(policy="ours", ...)` — this file now genuinely tests "the Phase 4 simulator" per Section 5's wording, not a separate module). Full output: 812 charging sessions over a 1000min/15-drone run, **0 mismatches** between predicted and realised start beyond the 1-tick tolerance (max observed deviation exactly 1.0, the tolerance boundary itself), with and without the priority ablation.
   - `tests/test_regression.py` (new, 5 tests): re-invokes the existing Phase 1/2 validation and both Phase 3 sanity checks (slack-zero reduction, Kleinrock conservation) by importing and calling their existing test functions (not forking a second copy), confirming they still pass after all of the above — plus the `policy="baseline"` exact-reproduction test (item 3 above).
   - Full suite: **`pytest -q` → 76 passed, 0 failed, 476.1s** (was 67 before this checkpoint; +9 new: 3 in `test_formulas.py` (F12), 1 in `test_ours_policy.py` (invalid combos), 5 in the new `test_regression.py`).
5. **Smoke run of every policy** (n_uavs=10, 5 stations×2 pads, horizon=300min, rate=0.4/min, `drain_cap_min=100`, 2 seeds — **labelled a smoke test, not a result**: no CRN-matched baseline comparison, no statistical rigor, purely "does every policy/ablation combination run without crashing or violating safety, and does F12 come out looking sane"):

   | policy | seed | completed/total | unfinished@cap | safety | sessions | F12 Z | C_max term | energy term | tardy term |
   |---|---|---|---|---|---|---|---|---|---|
   | baseline (B1/B2) | 1 | 109/109 | 0 | 0 | 15 | 1.9066 | 0.9933 | 0.9132 | 0.0000 |
   | baseline (B1/B2) | 2 | 138/138 | 0 | 0 | 17 | 1.9113 | 1.0067 | 0.9046 | 0.0000 |
   | jsq (B4) | 1 | 109/109 | 0 | 0 | 16 | 1.9603 | 0.9933 | 0.9669 | 0.0000 |
   | jsq (B4) | 2 | 138/138 | 0 | 0 | 18 | 1.9672 | 1.0100 | 0.9572 | 0.0000 |
   | ours (all on) | 1 | 109/109 | 0 | 0 | 120 | 1.9818 | 0.9900 | 0.9918 | 0.0000 |
   | ours (all on) | 2 | 138/138 | 0 | 0 | 151 | 2.0374 | 1.0100 | 1.0274 | 0.0000 |
   | ours, use_queue_term=False (B3) | 1 | 109/109 | 0 | 0 | 119 | 1.9787 | 0.9900 | 0.9887 | 0.0000 |
   | ours, use_reservation=False | 1 | 109/109 | 0 | 0 | 119 | 1.9787 | 0.9900 | 0.9887 | 0.0000 |
   | ours, use_priority=False | 1 | 109/109 | 0 | 0 | 120 | 1.9818 | 0.9900 | 0.9918 | 0.0000 |
   | ours, use_partial=False | 1 | 109/109 | 0 | 0 | 17 | 1.9254 | 0.9900 | 0.9354 | 0.0000 |
   | ours, use_jit=True | 1 | 109/109 | 0 | 0 | 122 | 1.9831 | 0.9900 | 0.9931 | 0.0000 |
   | ours, use_charge_time_term=False | 1 | 109/109 | 0 | 0 | 119 | 1.9787 | 0.9900 | 0.9887 | 0.0000 |

   All combinations: 0 safety violations, 0 unfinished-at-cap (drain worked), tardy term 0 (light load relative to the 45min deadline window — expected, not tuned). `use_partial=False`'s session count (17, close to baseline/jsq) versus every other ours-variant (~119-122) is the expected signature of partial charging causing far more, shorter sessions.

**Checkpoint 4, genuinely complete, 2026-09-22.** Not yet run: X3, X4, X6 (checkpoint 5, "the paper's main result") — awaiting review of this checkpoint first, per REMEDIATION.md's checkpoint discipline.

**Pre-X3 review, five items, 2026-09-22 (same day) — one real bug found and fixed, four confirmations:**

1. **Real bug found: F7/F9 predictions were NOT exact, and the deterministic-prediction test's 1-tick tolerance was hiding it.** The signed (not absolute) distribution of `realised_start − predicted_start` across all 812 sessions of the standard test scenario was entirely non-negative (realised never earlier than predicted) and bimodal: a continuous smear across (0,1) from raw travel/charge times never being rounded to the engine's tick grid, **plus a hard pileup of 252/812 (31%) sessions at exactly +1.0 tick** — all of them cases where the predicted start coincided with an exact tick multiple (commonly: a drone re-dispatched to the *same* station it had just finished charging at, τ_ij=0 exactly). Root cause: F7/F9 computed predictions from raw continuous travel time and F4's charge duration, but the engine can only ever register a state change at `t+DT_MIN`, never at a fractional or same-tick `t` — so a continuous prediction systematically understated the tick the engine would actually land on. **Fixed** by quantizing travel time and charge duration up to the tick grid (`_ceil_to_tick`, with a `DT_MIN` floor so even a same-tick dispatch is correctly predicted to take its true minimum one tick) at the point in `sim/mission_sim.py`'s `ours` branch where they feed F7/F8/F9 — the continuous math in `sim/formulas.py` itself is untouched. **Test tolerance tightened from 1.0 to exact (1e-9).** Re-verified: 794/794 sessions match exactly (session count shifts slightly from 812 because quantization changes a few F8 station-ranking ties — expected).
2. **F12 needs every released mission to finish; the smoke run's "0 unfinished_at_cap" was not automatically guaranteed.** Directly checked: for the smoke-run scenario at seed=1, `drain_cap_min=0` (off) already gives 0 unfinished (that seed's missions all happened to finish naturally) — but at seed=2, `drain_cap_min=0` leaves **2 unfinished**, closed to 0 only once `drain_cap_min=100` is supplied. So the smoke run's uniform "0 unfinished" was real but not automatic — it depended on the (explicitly set, and stated in the smoke-run header) `drain_cap_min=100`, not an accident of light load. **Decision, recorded here:** X3/X4 will call `run_mission_sim` with `drain_cap_min = 3 * deadline_window_min` (135min at the default 45min window) as their standard configuration — `run_mission_sim`'s own default stays `0.0` for backward compatibility/regression safety (checkpoint 4's exact-reproduction test depends on it).
3. **F8 ablation validity, now a permanent test:** `tests/test_regression.py::test_mission_list_identical_across_policies_and_ablations_at_fixed_seed` confirms that at a fixed seed, `mission_release_times`/`mission_destinations`/`mission_deadlines` are bit-for-bit identical across `baseline`, `jsq`, `ours` (defaults), and all six single-flag ablations — mission generation is a single shared code block run before any policy branch, and this test confirms that architecture actually holds in practice, so `use_queue_term=False` genuinely isolates the W_j term alone, not a different demand stream too.
4. **F5 gate binding rate:** now logged for every run (`gate_evaluations`, `gate_refusals`, `gate_binding_rate`), tracked uniformly across all three policies (baseline/jsq's per-station `_reachable` loop, ours' `station_gate` call). Smoke-run values range 0.27-0.60 across policies/seeds — the gate binds meaningfully, this isn't a trivially-always-reachable scenario. Also added while instrumenting this: `station` (which station index) and `request_time`/`total_delay_min` are now logged per charging session for **all three policies** (previously `ours`-only) — needed for X3's "mean/p95 charging delay" and "station utilisation" metrics to be computable uniformly.
5. **Confirmed, now a permanent test:** `tests/test_regression.py::test_policy_baseline_routes_to_nearest_reachable_station` — stations deliberately listed out of distance order (1500m, 1000m, 500m from the drone); `policy='baseline'` reliably picks the 500m one (index 2), proving it sorts by actual distance, not list position.

`pytest -q` → **78 passed** (76 + 2 new: the mission-list-identity test, the nearest-station test).

**Further pre-X3 build (2026-09-22, same day), approved by the user with 5 conditions:**
1. **Two missing X3 metrics built, each with its own test.** `mean_on_pad_queue_length` (time-integrated WAITING_FOR_PAD count / elapsed simulated time, uniform across all 3 policies) — hand-verified test: 2 co-located drones, 1 pad, drone 1 waits from t=1 to its own realised_start=32, expected mean=31/120, matches exactly. `runtime_per_decision_us` (wall-clock time around the dispatch-decision block only — F7-F11 for `ours`, the reachability+routing loop for baseline/jsq — divided by drones actually dispatched) — a smoke/sanity test only (can't hand-verify a wall-clock value): positive and well under 100ms/decision when dispatches occur, exactly 0.0 when none do.
2. **F12's C_max/ΣT_k now count unfinished-at-cap missions**, per the user's instruction: every mission still incomplete when the loop stops is treated as C_k = the actual elapsed simulated time at that point (not silently dropped, which understated both terms worst exactly when a policy is struggling). **Kept as separate fields** (`f12_makespan_capped_min`, `f12_tardiness_capped_min`, feeding `f12_Z`/`f12_cmax_term`/`f12_tardy_term`) rather than overwriting the legacy `makespan_min`/`total_tardiness_min`/`tardy_count` fields, which stay defined exactly as before (completed-missions-only) — those are depended on by `test_regression.py`'s exact-reproduction test, and one of its 3 golden configs has 1 unfinished mission, so redefining them in place would have silently broken backward compatibility.
3. **Session-level `station`, `request_time`, `total_delay_min` now logged for all 3 policies** (previously `ours`-only) — needed for X3's per-policy delay/utilisation metrics.
4. **`prediction_error_min` (= realised_start − predicted_start) now logged per session for `ours`-family runs**, explicitly, not just derivable, so X6 can consume X3's own session logs directly.

`pytest -q` → **80 passed** (78 + 2 new: `test_mean_on_pad_queue_length_hand_verified`, `test_runtime_per_decision_reported_and_sane`).

**X3 pre-registration (declared before running, per the user's explicit instruction and this project's own no-post-hoc-metric-shopping discipline):**
- **Primary metrics:** F12 total (Z) and deadline miss rate (`tardy_count` / `missions_total`, using the legacy completed-only definition for the miss-rate ratio itself, consistent with "miss rate" as a fraction of the demand actually observed).
- **Primary comparisons (3):** ours (all components on, JIT off) vs. baseline (B1/B2); ours vs. jsq (B4); ours vs. `use_queue_term=False` (B3 — "the key ablation for the queue-aware claim", REMEDIATION.md's own words).
- **Statistics:** paired Wilcoxon signed-rank on per-(layout, seed) differences for each of the 3 comparisons × 2 primary metrics (6 tests), **Holm correction applied within this family of 6** — not across the full metric/ablation table, which is secondary/exploratory and reported as such.
- **Everything else** (F12's C_max/energy terms individually, makespan, mean/p95 charging delay, on-pad queue length, station utilisation, energy per completed mission, safety violations, gate binding rate, runtime per decision, the other 5 ablations beyond B3) is **secondary** — reported, not Holm-corrected against the primary family, not used to claim significance on its own.

**X1 scope note (corrected 2026-09-22 — the version of this note that said R3b's ≥5-layout run was "not yet run" was stale; it's the section directly above):** X1 now covers R1, R3a, and R3b (≥5 layouts) with blocking probability and paired per-layout CIs reported. One piece remains dropped by decision:
- **R4 = R3a + JIT dispatch — decided 2026-09-22: dropped from X1.** In the queue-only model with random service times, JIT is non-work-conserving: with total delay counted correctly (E4(c)'s accounting rule — moving waiting off the pad must never make it disappear from the metrics), JIT can at best match R3a's total delay, never beat it, since there's no deterministic reservation to depart early for. A simulation here would only measure estimate error against an unknowable true start time, not a real scheduling effect. JIT is tested only where F7 actually holds — the `ours+JIT` variant in X3 and X4 (the CC-CV mission model), per the original Section 7 answer for those two experiments.

**Pre-remediation status and history:** the full 2026-09-21 (pre-`REMEDIATION.md`) phase-by-phase status, all validated numbers, and the seven bugs found during that work have moved to `HISTORY.md`. That file also carries the E10/E12/E13 corrections applied to the Phase 5 (MILP optimality-gap explanation) and Phase 6 (energy findings, H5 status) write-ups.

**Currently open decisions:**
1. Exact form of the flight power model — flat-rate κ=0.01 Wh/m is in use and validated; the fuller P(v,m) form (Section 4.3) is coded behind the `ENERGY_MODEL` switch but not yet calibrated (needs hardware data, Section 14.8). Still genuinely open.

**Settled decisions (for reference — full history and reasoning in `HISTORY.md`):** does W_j enter the MILP (no, kept implicit); C9/C10 formal statements (implemented in `solve_charge_schedule_milp_ccv`, though E8/E9 remain open per Section 4.5 above); slack distribution in Phase 3 (Exponential, mean=1/μ); Phase 3 priority weights (pure least-slack-first, w1=1,w2=0 — superseded for the F11 heuristic by the Section 7 answer, w1=w2=1); R3b/R3a geometry (2000m×2000m area, fixed random station layout seed=0, 15 m/s); the Section 7 open decisions (energy model, JIT default, F12 objective, F11 weights, 2-leg origin decision) all recorded above in this section.

### Checkpoint 5, X3: our method vs baselines (2026-09-22)

**Run:** `experiments/x3_baselines_vs_ours.py`, 9 policies × 5 configs × 30 (layout, seed) pairs (5 random layouts × 6 seeds each, every policy on the same pairs) = 1350 runs, 1921.8s (~32min, matching the 2-seed pilot's estimate closely). Raw CSV: `results/x3_full_20260922_223809.csv`. n_uavs=20, horizon=1000min, `drain_cap_min=135` (3×deadline_window_min). 0 safety violations across all 1350 runs.

**Pre-registered primary result (F12 Z and miss rate, ours vs baseline/jsq/B3, paired Wilcoxon + Holm within each config's 6 tests): `ours` does NOT dominate.** Full per-policy means (F12 Z / miss_rate / unfinished_at_cap, out of ~795 missions for density configs, ~301 for light, ~1600 for saturated):

| config | baseline Z / miss / unfin | jsq Z / miss / unfin | **ours** Z / miss / unfin | B3 (queue_term=False) Z / miss / unfin |
|---|---|---|---|---|
| density_scarce | 2.410 / 0.107 / 30.4 | 2.005 / 0.006 / 0.0 | **2.950 / 0.215 / 10.7** | 2.552 / 0.000 / 0.0 |
| density_balanced (nominal) | 2.021 / 0 / 0 | 2.046 / 0 / 0 | **2.410 / 0 / 0** | 2.368 / 0 / 0 |
| density_abundant | 2.011 / 0 / 0 | 2.045 / 0 / 0 | **2.247 / 0 / 0** | 2.235 / 0 / 0 |
| load_light | 1.998 / 0 / 0 | 2.025 / 0 / 0 | **2.330 / 0 / 0** | 2.321 / 0 / 0 |
| load_saturated | 2.949 / 0.287 / 102.0 | 2.092 / 0.024 / 0.9 | **2.557 / 0.022 / 0.0** | 2.392 / 0.00002 / 0.0 |

**Two findings, both reported plainly rather than tuned away:**

1. **F12 Z is higher for `ours` than baseline/jsq/B3 in 4 of 5 configs (all Holm-adjusted p≤1.1e-8) — driven entirely by the energy term** (`ours` energy term 1.2-1.55 vs baseline's 0.95-1.09, jsq's 1.0-1.05; the C_max term is ~1.0-1.06 for everyone, not the driver). This is the same partial-charging energy penalty already established in Phase 4/6 (`HISTORY.md`) — more frequent, shorter charging trips under `use_partial=True` cost more total energy than always-charging-to-full, now reproduced inside the correctly-implemented F12 framework rather than the old ad hoc energy comparison. Only in `load_saturated` does `ours` beat baseline on Z (2.557 vs 2.949) — baseline's naive threshold+nearest dispatch catastrophically backlogs there (unfinished_at_cap=102.0 on average, vs ≤0.9 for every smarter policy), which dominates baseline's own Z via the capped C_max/tardiness terms.
2. **In `density_scarce`, `ours` has the WORST miss rate of the four primary policies (0.215), including nearly 3x worse than plain baseline (0.107)** — and `B3 (use_queue_term=False)` achieves **0.000**, the best of all nine policies tested. This directly contradicts the project's central queue-awareness hypothesis: REMEDIATION.md calls B3 "the key ablation for the queue-aware claim," and here removing queue-awareness *helps*, sharply. **Isolated by running the full ablation set in this config**: turning off `use_queue_term`, `use_reservation`, or `use_charge_time_term` *individually* each independently drops miss rate to ~0.000; turning off `use_priority` (0.224) or `use_partial` (0.352, worse) does *not* fix it. This points at F8's combined cost `J = τ_ij + W_j + T_chg` specifically (not priority ranking, not partial charging) as the mechanism — plausibly a thundering-herd effect where multiple drones' W_j/T_chg-based rankings agree on the same "currently least-busy" station under scarce-station contention, overloading it, though this is a hypothesis, not yet verified. **Not investigated further — flagged for the user rather than root-caused unilaterally**, since it bears directly on whether X4 (which compares layouts *using* these same policies) is even meaningful to run before this is understood. An "effective miss rate" that also counts `unfinished_at_cap` as missed (since baseline's low completed-only miss rate is partly an artifact of leaving ~30 missions permanently unstarted) makes the same ranking sharper: baseline 0.145, jsq 0.006, **ours 0.228**, B3 0.000.

**Full CSV has all 9 policies × 26 columns** (config, per-policy F12 terms, legacy and capped makespan/tardiness, mean/energy fields, gate binding rate, on-pad queue length, runtime per decision, session counts) for further analysis.

**Root cause of finding 2, 2026-09-23 (before touching X4, since X4's concentrated arm is itself a scarce-station case that would inherit the problem).** Four diagnostics, cheapest first, on the worst-case (layout=4, seed=29) `density_scarce` pair (miss_rate=0.602, unfinished=98):

1. **F7 exactness, checked specifically in this config (never checked here before, only on a balanced config): exact.** 981 sessions, 0 deviations — rules out a prediction bug entirely, including in the actual failing scenario, not just the easy one.
2. **F9 reservation lifecycle audit: clean, no leak, no abandonment.** By code inspection: `reservation[uav.id]` is written exactly once (Step 3) and deleted exactly once, on successful completion (Step 8) — no other write or delete path exists anywhere in the engine, so a reservation can never be silently abandoned mid-run. `free_time[pad]` is analytically monotonic non-decreasing: the chosen pad is always `argmin(free_time)`, so `best_start >= free_time[pad]` (old value) and `end = best_start + T_chg >= best_start`, hence `end >=` the old value — it cannot decrease. Empirically confirmed: 981 reservations created, 963 honoured, 18 pending — and 963+18=981 exactly, with the 18 pending explained entirely as still-active reservations when the simulation ended (a boundary effect, not a leak).
3. **Real mechanism found: `ours` sends drones on real, uncompensated detours.** New opt-in `collect_dispatch_diagnostics=True` records, per dispatch decision, the chosen station vs. the nearest reachable one. In the worst-case pair: `ours` picks a non-nearest station on **28.7% of decisions** (mean extra travel +128.5m across all decisions), while `B3 (use_queue_term=False)` picks the nearest station **100% of the time** (0% non-nearest, by construction — dropping the queue term collapses F8 to pure τ_ij+T_chg ranking, which for two similarly-equipped stations reduces to nearest-station). **Reproduced on a second, independent bad layout** (layout=1, seed=11): 17.3% non-nearest, +118.4m extra, miss_rate=0.559 vs B3's 0.000 — not a single-layout fluke.
4. **Per-drone correlation between detour frequency and mission-miss frequency: positive but weak (r=0.29), not a clean 1:1 link.** Drones with a higher non-nearest fraction do trend toward worse mission outcomes, but even the LEAST-detouring drone in the worst-case run (17.3% non-nearest) still has a 65% bad-mission rate — the degradation is spread across the whole fleet, not confined to the specific drones that detour. This is consistent with a **system-level congestion effect**: with only 4 total pads (2 stations × 2 pads) for 20 drones, the extra flight time/energy from `ours`'s detours is enough to tip the whole shared-capacity system into a self-reinforcing backlog, not just cost the detouring drone itself.

**Conclusion (revised 2026-09-23 — see attribution correction below): not a bug — a real, reportable limitation, in F9's ordering as much as F8's cost.** All four diagnostics point the same way: F5-F9's bookkeeping is exact and leak-free (diagnostics 1-2 clean); the degradation is fully explained by real routing choices that trade a *predicted* time-to-ready improvement for *uncompensated* extra travel distance (diagnostic 3), whose cost compounds under scarce shared capacity into fleet-wide backlog (diagnostic 4).

**Attribution correction (2026-09-23, caught by the user):** the first write-up above named F8 alone. `use_reservation` is **F9**, not F8, and disabling F9 also fixes the problem — that implicates F9 (or the F8/F9 interaction), not F8 in isolation. Tested directly with new instrumentation (`priority`, `ahead_lower_priority`, `ahead_total` now recorded on every reservation and copied into `session_log`): the user's hypothesis was **F9 commits a pad slot at reservation time and appends it to that pad's queue in creation order — service across epochs is FCFS-by-reservation-time, and F10/F11's priority ranking only orders drones *within* one epoch. Under scarce pads this is priority inversion: a drone whose reservation was created 20 minutes ago holds a slot that a drone arriving 5 minutes from now, and far more urgent, cannot jump ahead of.**

**Direct test, worst-case pair (layout=4, seed=29), `ahead_lower_priority` = count of currently-pending same-pad reservations with priority below this drone's, at the moment its own reservation was created:**
- 700/963 sessions (72.7%) had `ahead_lower_priority > 0` — a majority of all reservations in this run were queued behind at least one less-urgent one.
- Sessions with inversion → next-mission bad (late/unfinished) rate **79.3%**; sessions without inversion → **58.1%** — a 21-point gap.
- **Clean, monotonic dose-response** linking the two (not just a threshold effect):

  | `ahead_lower_priority` | n sessions | bad-mission fraction |
  |---|---|---|
  | 0 | 234 | 0.581 |
  | 1 | 159 | 0.730 |
  | 2 | 150 | 0.700 |
  | 3 | 110 | 0.864 |
  | 4+ | 137 | 0.912 |

  **Hypothesis confirmed.** (The 0.581 floor at zero inversions confirms this isn't the *only* driver — general scarce-capacity overload contributes a high baseline miss rate regardless — but inversion clearly makes it substantially worse on top of that.)

**Two F9 variants implemented as opt-in flags** (`f9_priority_insertion: bool = False`, `f9_lookahead_cap_min: float = None`, both default off — **current behaviour stays the default, X3's result stands exactly as reported**):
- **(a) Priority-aware insertion** (`f9_priority_insertion=True`): a new reservation may be inserted ahead of not-yet-started (not yet physically `CHARGING`) lower-priority reservations at the same pad; already-charging reservations can't be preempted. Implemented as a full re-sort-and-cascade of each pad's pending-reservation chain (`start`/`end` recomputed for every entry from the insertion point onward), not just a front-of-queue hack.
- **(b) Bounded lookahead** (`f9_lookahead_cap_min=L`): refuse to commit to a reservation whose predicted start is more than `L` minutes ahead of now; the drone stays in "needs charging" state and is re-evaluated next epoch, when the queue picture may have changed.

**Full `density_scarce` re-run (all 30 layout/seed pairs, not just the worst one), mean across pairs:**

| policy | mean miss_rate | mean unfinished_at_cap | mean F12 Z |
|---|---|---|---|
| baseline | 0.1066 | 30.4 | 2.410 |
| jsq | 0.0058 | 0.0 | 2.005 |
| **ours (current default)** | **0.2149** | **10.7** | **2.950** |
| B3 (use_queue_term=False) | 0.0000 | 0.0 | 2.552 |
| **ours + (a) priority-aware insertion** | **0.2711** | **16.7** | **3.082** |
| **ours + (b) bounded lookahead, L=15** | **0.0013** | **0.0** | **2.519** |

**(a) does not help — it's slightly worse than doing nothing** (0.271 vs 0.215 miss rate, more unfinished). This makes sense in hindsight: reordering *who* is served first at a pad doesn't change the *total* amount of queueing time the pad's whole backlog represents (the same conservation-law intuition already established for H1 earlier in this project) — it only redistributes delay among drones, and here the redistribution itself adds overhead (thrashing) rather than net good.

**(b) is a dramatic, near-complete fix** — miss rate 0.2149→0.0013, unfinished 10.7→0.0, F12 Z 2.950→2.519 (below B3's 2.552). `L` was scanned on both bad layouts (layout=4/seed=29 and layout=1/seed=11) at L∈{5,10,15,20,25,30}: **L∈[5,20] is a stable, near-perfect plateau on both layouts; L=25 already degrades sharply on one layout, L=30 is nearly as bad as no cap at all (0.652 miss rate, worse than unbounded `ours` on one layout).** This is a real threshold effect, not a smooth trade-off — L=15 (chosen for the table above, a third of the 45min deadline window) sits safely inside the plateau on both tested layouts, but the sharp cliff at L≈25 means this is not yet a robustly-tuned parameter, just a demonstrated existence proof that bounding lookahead fixes the mechanism.

**Conclusion:** the root cause is confirmed to be F9's rigid FCFS-by-creation-time ordering interacting with F8's detour-prone routing — a genuine reservation-system design limitation, not a bug, and not primarily an F8 cost-formula problem as the first pass suggested. A bounded-lookahead variant of F9 fixes it convincingly in this config; a priority-reordering variant does not. Both are implemented, tested, and available as opt-in flags; **current (unbounded, FCFS) F9 remains the default**, so X3's reported numbers are unaffected. The positioning-aware F8 variant proposed in the first pass (`J' = J + λ·d(station, next mission)/v`) is still a reasonable idea independently (diagnostic 3's detour-distance finding is real and unaffected by this correction), but is no longer the primary fix — not implemented, available if wanted.

### Checkpoint 5, X4: layout crossover in the mission model (2026-09-23)

**⚠ B3's row in this section is INVALIDATED by the pad-capacity bug above (fixed 2026-09-23) — see the corrected re-run further down. `ours`, `baseline`, and `jsq` rows are unaffected and stand as reported (none of them ever set `use_queue_term=False`).**

**Run:** `experiments/x4_layout_crossover.py`, narrowed to 4 pre-registered primary policies per the user's instruction (baseline, jsq, ours, B3), × 2 layout arms (concentrated: 1 station × 10 pads; distributed: 10 stations × 1 pad each — same total capacity, distributed positions identical to X3's "abundant"-density layouts, concentrated hub at each layout's centroid) × 7 load points (0.3–1.6/min) × 30 (layout, seed) pairs = 1680 runs, 2282.8s (~38min, pilot estimated 42.6min). Current (default, FCFS) F9 behaviour throughout — the priority-inversion fix above was **not** applied here. Raw CSV: `results/x4_full_20260923_051104.csv`. **0 safety violations across all 1680 runs.**

**Headline: whether the crossover survives depends entirely on the policy, and the direction can reverse or vanish.**

| policy | pattern (mean charge delay, concentrated vs. distributed, across load 0.3→1.6) |
|---|---|
| baseline (B1/B2) | **No crossover — concentrated always wins**, by a growing margin (1.18 vs 3.56 → 2.12 vs 56.52min). Distributed's p95 delay explodes (17.7→233min) and starts leaving missions permanently unfinished from rate=1.1 up (13.4→253.1 mean unfinished) — naive nearest-station dispatch on 10 unpooled single-pad stations is a real bottleneck under load, matching classical pooling superiority (consistent with the R3a finding in the queue-only model). |
| jsq (B4) | **No crossover — concentrated always wins**, but JSQ narrows the gap sharply vs. baseline (distributed p95: 2.4→61.3min, vs. baseline's 17.7→233min) and only barely misses missions at the highest load tested (1.6 mean unfinished at rate=1.6). Smart routing softens but does not reverse the pooling advantage. |
| **ours** | **A genuine crossover appears.** Distributed wins at low-moderate load (mean delay 1.07-1.29 vs. concentrated's 1.34-1.41 at rate 0.3-0.9; p95 1.31-2.67 vs. flat 2.0), concentrated takes over from rate≈1.1-1.3 up (mean 1.48-3.01 vs. 1.41-2.01; by rate=1.6, p95 7.23 vs. 4.27). Small unfinished (2.6 mean) only at the highest load tested. This is the shape of the reference paper's own result, reproduced for a genuinely different reason (see caveat below). |
| B3 (use_queue_term=False) | **No crossover — distributed always wins**, robustly and by a wide, stable margin at every load tested (mean delay ~1.01 vs. concentrated's 1.34-1.37, essentially flat across the whole 0.3-1.6 range; p95 pinned at ~1.0-1.015 vs. concentrated's flat 2.0). Zero unfinished missions anywhere. |

**Unfinished-at-cap confirms the story precisely**: 10134 (baseline/distributed) + 49 (jsq/distributed) + 77 (ours/distributed) + 0 everywhere else, out of 10260 total across all 1680 runs — concentrated arms and B3's distributed arm never fail to keep up; only the naive-routing distributed arms do, and only at high load.

**Interpretation, first pass (2026-09-23) — corrected below, kept for the record.** Partial charging (shared by `ours` and B3, `use_partial=True`) was proposed as what makes the distributed layout fundamentally more efficient than concentrated — shorter, more localized sessions cut travel and pad-occupancy time. **This was never actually isolated** (B3 differs from baseline/jsq on routing, priority, and reservations too, not just partial charging) and is corrected below.

### X4 follow-up (2026-09-23, same day): is the crossover an artifact of the F9 defect, and is "partial charging" really the driver?

**⚠ Every check in this subsection that involves B3 (checks 1 and 3, and the F9-variant re-run of `ours`'s own `use_queue_term=False` sub-path where applicable) is INVALIDATED by the pad-capacity bug above. Check 2 (priority-inversion diagnostic on plain `ours`, no B3 involved) is unaffected. See the corrected re-run further down.**

Three things checked directly, per the user's instruction, before accepting the X4 headline:

**1. Re-ran `ours` across the identical X4 grid (same 30 pairs, 7 loads, both arms) with both F9 variants — 840 runs, `results/x4_ours_f9_variants_20260923_155026.csv`. The crossover survives essentially unchanged:**

| rate | unfixed (original X4) | + priority-aware insertion | + bounded lookahead L=15 |
|---|---|---|---|
| 0.3 | conc=1.34 dist=1.07 → **distributed** | conc=1.34 dist=1.07 → **distributed** | conc=1.34 dist=1.07 → **distributed** |
| 0.9 | conc=1.37 dist=1.29 → **distributed** | conc=1.37 dist=1.32 → **distributed** | conc=1.37 dist=1.29 → **distributed** |
| 1.1 | conc=1.41 dist=1.48 → **concentrated** | conc=1.41 dist=1.51 → **concentrated** | conc=1.41 dist=1.45 → **concentrated** |
| 1.6 | conc=2.01 dist=3.01, miss=0.066 → **concentrated** | conc=2.25 dist=3.05, miss=0.066 → **concentrated** | conc=2.01 dist=2.87, miss=0.016 → **concentrated** |

**This is the opposite of X3's outcome.** In `density_scarce` (2 stations), bounded lookahead was a dramatic, near-complete fix (miss rate 0.215→0.0013). Here (10 stations, the distributed arm), the same fix barely moves anything — the crossover point, and almost all of the delay values, are unchanged to 2 decimal places; only the rate=1.6 miss rate drops somewhat (0.066→0.016, still nonzero). **Conclusion: the X4 crossover is not an artifact of the F9 priority-inversion defect.** It survives both attempted fixes essentially intact, so — per the next check — it must be driven by something else.

**2. Priority-inversion diagnostic run directly on `ours` (default F9) at the loads where concentrated overtakes distributed (rate=1.1, 1.3, 1.6), all 30 pairs, `experiments/x4_ours_priority_inversion_check.py`:**

| rate | sessions | fraction w/ inversion | bad-mission fraction by `ahead_lower_priority` |
|---|---|---|---|
| 1.1 | 42,858 | 9.3% | **0.000 at every level (0,1,2,3,4+)** — no misses to explain yet |
| 1.3 | 51,083 | 15.0% | **0.000 at every level** — still no misses |
| 1.6 | 62,107 | 32.1% | 0→5.8%, 1→7.9%, 2→9.7%, 3→17.0%, 4+→**46.2%** — same monotonic dose-response shape as X3, much milder in magnitude (X3: 58%→91%; here: 5.8%→46%) |

**This resolves the apparent contradiction with check 1.** At rate=1.1 and 1.3, the mean-delay crossover has already happened, but there are *zero* actual missed missions at any inversion level — the delay gap (1.45-1.51min vs 1.41min) is real but too small to blow any 45-minute deadline windows, so there is nothing for priority inversion to be "causing" yet. Only at rate=1.6 do real misses appear, and there the *same* mechanism as X3 is clearly operating (the monotonic dose-response is the signature), just far milder — consistent with 10 stations not being scarce. **So: the F9 defect does contribute a small, real, correctly-diagnosed effect at the highest load tested, but it is not what creates the crossover itself** — the crossover in mean/p95 delay is a broader, more fundamental phenomenon (most likely ordinary pooling dynamics: 1 pad per station bottlenecks under rising load, exactly like an M/M/1 queue per station, while concentrated pools into 10 parallel pads, an M/M/10-style queue that absorbs the same load far more gracefully — independent of any reservation-ordering detail).

**3. `B3 + use_partial=False` run across the identical X4 grid, `results/x4_b3_partial_false_20260923_154305.csv` — refutes the "partial charging" claim directly.** With partial charging removed (full charge every time, same nearest-station routing / F9 reservations / F10-F11 priority as B3), the pattern is **essentially unchanged from B3 itself**: distributed wins at *every* load, flat and robust (mean delay conc≈1.48-1.50 vs dist≈1.02-1.03 across the whole 0.3-1.6 range, vs. B3's own conc≈1.34-1.37 vs dist≈1.01). **Partial charging is not the driver.** The real common factor across B3 and B3-without-partial-charging (and absent from baseline/jsq) is the **reservation-based, deterministic scheduling itself** — F7's exact wait-time tracking plus F9's reservation queue plus nearest-station routing plus F10/F11 priority-based mission assignment — which lets every one of these policies plan around exact, known pad-availability instead of discovering contention only on physical arrival (baseline/jsq's mode). That combination, not partial charging specifically, is what makes distributed layouts robustly efficient wherever it's present (B3, B3-no-partial), and it is *queue-awareness* (F8's W_j term, the one thing separating `ours` from B3) that reintroduces the load-dependent crossover on top of it.

**Revised interpretation, replacing the first pass above:** the reservation-based deterministic scheduling shared by B3/`ours`/B3-no-partial (not partial charging) is what makes distributed layouts robust; queue-awareness (F8, present only in `ours`) is what reintroduces a genuine, load-dependent crossover on top of that — and that crossover has now been shown to survive both attempted F9 fixes, so it is a real property of `ours`'s design (specifically F8's cost function, not F9's ordering), not an artifact of the priority-inversion defect X3 found.

**4. X6 (prediction accuracy), using the already-logged `prediction_error_min` field — REMEDIATION.md's X3 grid, `ours`, default F9, `experiments/x6_prediction_accuracy.py`: 154,726 completed sessions across all 5 X3 configs, 154,726 exact matches, 0 nonzero.** F7's prediction is exact at full scale, not just in the earlier spot-checks.

### Pre-X5 checks (2026-09-23)

**⚠ Both checks in this subsection use B3 and are INVALIDATED by the pad-capacity bug above. See the corrected re-run further down.**

**1. B3 utilisation sanity check — flat ~1.01min delay validated, not an artifact of B3 doing less work.** `experiments/x4_b3_baseline_utilization_check.py`, distributed arm, all 30 pairs, X4's 7 load points:

| policy | rate | completed/total | unfinished | station util | sessions/drone | mean delay (min) |
|---|---|---|---|---|---|---|
| baseline | 0.3 | 301.5/301.5 | 0.0 | 0.136 | 2.18 | 3.56 |
| baseline | 0.9 | 894.3/894.3 | 0.0 | 0.407 | 6.49 | 19.10 |
| baseline | 1.6 | 1346.8/1599.9 | **253.1** | 0.619 | 9.83 | 56.52 |
| B3 | 0.3 | 301.5/301.5 | 0.0 | 0.091 | 19.34 | 1.012 |
| B3 | 0.9 | 894.3/894.3 | 0.0 | 0.281 | 57.61 | 1.014 |
| B3 | 1.6 | **1599.9/1599.9** | **0.0** | 0.509 | 102.14 | 1.015 |

At rate=1.6, B3 completes **every** mission (0 unfinished, vs baseline's 253.1) while running at **lower** station utilisation (0.509 vs 0.619) and ~10x more sessions/drone (102 vs 9.8, from partial charging). B3's flat delay is not free — it is genuinely servicing all the demand baseline drops, via many more, shorter, reservation-scheduled sessions, and still keeping delay flat. The flat-delay finding holds.

**2. Attribution narrowing (F9 vs F10/F11), inconclusive — neither alone is necessary.** `experiments/x4_b3_attribution_variants.py`, full X4 grid, both variants (840 runs each, `results/x4_b3_attribution_20260923_164112.csv`):

- `B3_no_reservation` (`use_reservation=False`, everything else as B3): distributed still wins at every rate, flat (conc≈1.34-1.37, dist≈1.01, 0 misses) — indistinguishable from full B3.
- `B3_no_priority` (`use_priority=False`, everything else as B3): same result, indistinguishable from full B3.

Combined with the earlier `use_partial=False` check (also indistinguishable from full B3, Section above), **removing any single one of {reservation (F9), priority (F10/F11), partial charging} from B3 leaves the distributed-wins pattern unchanged.** The pattern is either overdetermined by these three components jointly, or driven by something none of them ablate individually — most likely F5/F6's gate-based nearest-reachable-station dispatch and F7's deterministic wait tracking themselves (both always-on in `ours`/B3, never toggled by these three flags, and structurally different from baseline's simpler dispatch). **Not yet isolated — reported as open, per the instruction not to overclaim.** The safe statement remains: "reservation-based, deterministic scheduling with nearest-station routing (F5-F9)" drives the effect, without attributing it to any one sub-mechanism.

### X5 — energy decomposition and H5, done (2026-09-23)

`experiments/x5_energy_and_h5.py`, 4 policies (`ours_partial`, `ours_full`, `baseline_adaptive`, `baseline_full`) x 7 configs (fleet 12/20/40 holding 4 drones/station fixed; density scarce/balanced/abundant; load light/nominal/saturated, sharing the n=20/5-station/rate=0.8 centre point) x 30 pairs (5 layouts x 6 seeds) = 840 runs, 1052.2s. Raw: `results/x5_full_20260923_164826.csv`.

**H5 test (makespan, miss rate — not energy, per E12).** Miss rate is only non-trivial (i.e. actually tests anything) in `density_scarce` and `load_saturated`; every other config saturates to ~0 misses for all four policies:

| config | ours_partial | ours_full | baseline_adaptive | baseline_full |
|---|---|---|---|---|
| fleet_12 | makespan=1006.0 miss=0.0004 | makespan=1001.1 miss=0.0000 | makespan=**1106.4** miss=**0.0539** | makespan=1002.5 miss=0.0019 |
| density_scarce | makespan=1084.7 miss=**0.290** | makespan=1111.9 miss=0.377 | makespan=1100.0 miss=**0.047** | makespan=1051.9 miss=0.122 |
| load_saturated | makespan=1014.1 miss=0.033 | makespan=1017.1 miss=0.029 | makespan=1090.2 miss=**0.086** | makespan=1124.6 miss=**0.410** |

**H5 ("partial/adaptive charging reduces makespan and misses most at high load") is only partly supported, and the direction flips by config — not a clean confirmation.**
- `density_scarce` and `load_saturated` (the two stress configs) both show adaptive/partial charging *reducing* miss rate for **baseline** — sharply at `load_saturated` (0.086 vs 0.410, ~5x), consistent with H5's "most at high load" framing.
- For `ours`, the same direction barely shows at `density_scarce` (0.290 vs 0.377, partial better) but *reverses* at `load_saturated` (0.033 vs 0.029, partial marginally worse) — no consistent benefit for the modern heuristic at all.
- `fleet_12` shows baseline_adaptive **doing much worse than full** on both makespan (1106 vs 1003) and miss rate (0.054 vs 0.002) — the opposite of H5's prediction. **Not a low-stress config** (5.4% miss rate is real contention) — diagnosed below.
- **Verdict (restated, 2026-09-23, replacing "mixed" with the actual pattern): partial/adaptive charging helps under stress for baseline (density_scarce, load_saturated), and is neutral for `ours` everywhere tested — plausibly because `ours` already schedules charging proactively (F5's lookahead-based trigger dispatches a drone before it's forced to, unlike baseline's purely reactive SoC-threshold trigger), leaving little slack for partial charging's shorter-session strategy to add on top. `ours`'s own scheduling absorbs most of the benefit partial charging would otherwise provide; baseline's naive reactive dispatch does not, so partial charging still has room to help there. `fleet_12` is the third data point and reverses baseline's pattern — diagnosed below, not set aside.**

**`fleet_12` reversal, diagnosed (2026-09-23):** same drones-per-station (4.0) and pads-per-drone (0.5) ratio as `fleet_20_centre`, which shows near-zero miss for both variants — so the ratio doesn't explain it. Direct comparison, 30 pairs, `fleet_12`'s exact config (n=12, 3 stations, 6 total pads, rate=0.8):

| policy | util | sessions/drone | unfinished | miss rate | completed |
|---|---|---|---|---|---|
| baseline_adaptive | 0.377 | 44.12 | 34.73 | 0.0539 | 757.4 |
| baseline_full | 0.618 | 9.74 | 0.00 | 0.0019 | 792.2 |

Adaptive runs **~4.5x more sessions/drone** (44.1 vs 9.7, the usual shorter-partial-charge signature) yet ends at **lower** utilisation (0.377 vs 0.618) and leaves 34.73 missions unfinished (vs 0 for full). The extra travel-to-pad overhead from far more frequent trips is the same mechanism X5's energy decomposition already shows in every config — but at only 12 drones total (the smallest fleet size tested, and 6 total pads), there is too little fleet-wide demand to statistically absorb that overhead the way `density_scarce` (20 drones, fewer pads per drone but 20 total drones' worth of demand to pool across) or `load_saturated` (20 drones, high rate) can. **This is a genuine small-fleet effect, not a data artifact or a "low-stress" mislabel** — the smaller absolute fleet size means individual pile-ups in adaptive's much larger number of shorter sessions aren't smoothed out by pooling across enough drones, so the per-trip overhead cost dominates instead of being absorbed. Not fully resolved to one clean statistic beyond this, but the mechanism (overhead cost vs. fleet-size-dependent pooling capacity) is the same one already established for the sign-reversal finding in `HISTORY.md`'s Phase 6 (fleet-size 5/10 → 20/40/60 reversal), now seen again at a third, independently-run configuration.

### Critical finding: B3's entire result set is invalidated by a pad-capacity bug (2026-09-23)

**In response to the routing-isolation test requested above, a real bug was found in `sim/formulas.py::time_to_ready_cost` that invalidates every B3 (`use_queue_term=False`) result reported so far** — X3's `density_scarce` 0.000 miss rate, X4's "distributed always wins" B3 row, the `B3+use_partial=False` check, and both `B3_no_reservation`/`B3_no_priority` attribution runs. `ours` (default, `use_queue_term=True`) is **not** affected — see below.

**The bug:** `time_to_ready_cost` (`sim/formulas.py:72-87`):
```python
if use_queue_term:
    W_j, start, best_pad = deterministic_wait(free_time_by_pad, t_arr)
else:
    W_j, start, best_pad = 0.0, t_arr, min(range(len(free_time_by_pad)),
                                            key=lambda p: free_time_by_pad[p])
```
When `use_queue_term=False` (B3's defining flag), `start` is unconditionally set to `t_arr` (the drone's own arrival time) — `free_time_by_pad` is only consulted to pick *which* pad (`best_pad`), never to check whether that pad is actually free. REMEDIATION.md's own definition of B3 ("nearest-time greedy... no W_j in the *cost*") means queue length should be dropped from the *ranking* between stations, not that physical pad occupancy (C1) should stop being enforced at all — but that's what the code does.

**Consequence, verified directly:** at the X4 grid's rate=1.6/distributed-arm stress point (seed=1, layout=0), **all 10 of 10 single-pad stations show overlapping charging sessions, up to 5 UAVs "charging" concurrently at one physical pad.** B3's flat, near-perfect result across every load and every config tested was drones being allowed unlimited concurrent occupancy at capacity-1 pads, not a genuine scheduling win.

**This also fully explains the "inconclusive" attribution finding from the section above, more precisely than "overdetermined":** `use_reservation`'s effect (updating `free_time`) can only ever matter through the `use_queue_term=True` branch of `time_to_ready_cost` (the only place `free_time_by_pad`'s *values*, not just which pad has the min, are read) — so with `use_queue_term=False` already set (B3's own definition), toggling `use_reservation` is provably a no-op, not a live ablation that happened to show no effect. `B3_no_reservation`'s identical-to-two-decimals result was never really a test of F9 in isolation. The "routing is the driver" hypothesis (this section's original request) is also not directly answerable this way: the `ours_all_off` variant launched below inherits the same bug (it also sets `use_queue_term=False`), so its flat result is equally an artifact, not evidence about routing.

**What is NOT affected:** `ours` at default settings (`use_queue_term=True`) always calls `deterministic_wait`, which does respect `free_time_by_pad`'s actual values (`start = max(t_arr, free_time[best_pad])`) — X4's headline "`ours` shows a genuine crossover" result, and X5's `ours_partial`/`ours_full` comparisons (which never set `use_queue_term=False`), are unaffected by this bug and stand as reported.

**Fixed 2026-09-23, per user instruction.** `time_to_ready_cost`'s `else` branch now reads `start = max(t_arr, free_time_by_pad[best_pad])` — drops only the `W_j` *cost* term from B3's station ranking, exactly as B3 is defined; pad occupancy is respected as a floor on `start`, not ignored. F7/F9's reservation mechanics (how `free_time` itself is computed and updated) are untouched.

**Two permanent guards added, both now part of every run:**
1. **Hard capacity invariant** (`sim/mission_sim.py`, end of the per-tick loop): every tick, for every station, counts UAVs with `state=="CHARGING"` and raises `AssertionError` if it ever exceeds `num_pads` — for every policy, every flag combination, unconditionally. A violation now fails the run instead of producing a silently-wrong number.
2. **Flag-effect test** (`tests/test_ours_policy.py::test_every_ablation_flag_changes_observable_behaviour`): on a contended config (20 drones, 2 stations x 2 pads, rate=1.2), flips each of the six ablation flags one at a time and asserts at least one of six summary metrics (completions, sessions, energy, F12 Z, unfinished, mean delay, mean on-pad queue length) differs from default — the same shape of check that would have caught `use_reservation`'s B3 no-op immediately. **This test itself caught a real gap on first write**: the original 6-metric summary showed `use_jit=True` as a no-op too, because JIT is designed to move delay off-pad without changing total delay (by design, per `test_F14_jit_preserves_total_delay_but_removes_onpad_wait`) — the summary needed `mean_on_pad_queue_length` added before it correctly showed JIT's effect. All six flags now pass.

**Adding the capacity invariant immediately surfaced a second, related violation**, independent of B3: with `use_queue_term=True` (default `ours`) but `use_reservation=False`, `free_time` is initialised once and never updated (since the update is gated by `use_reservation`), so `deterministic_wait` computes every pad as permanently free — `test_all_ablations_run_safely` and the F9 stampede test both immediately failed with 6 UAVs simultaneously "charging" at a 1-pad station. **Fixed with a physical occupancy backstop** at the two places `sim/mission_sim.py` transitions a UAV to `CHARGING` (arrival, and waiting-for-pad→charging): both now additionally require the station's current `CHARGING` count to be under its pad capacity before allowing the transition, exactly mirroring baseline/jsq's own `pads_busy` check — a hard safety net independent of any scheduling flag, not a change to F9's reservation bookkeeping. `pytest -q` → **81 passed** (80 + 1 new), including the full suite (Phase 1-5, MILP, all regression tests) with zero regressions.

**Routing-isolation experiment (`experiments/x4_ours_all_off.py`, 420 runs) was launched before this bug was found; its results are subject to the (now-fixed) bug and were discarded, not analysed.**

### X3 density_scarce, re-run post-fix (2026-09-23) — the original headline finding reverses

`experiments/x3_density_scarce_rerun.py`, all 9 policies, same 30 (layout, seed) pairs as the original X3 run, 179.1s. Raw: `results/x3_density_scarce_rerun_20260923_210050.csv`. **0 safety violations across all 270 runs** (the new hard invariant ran on every tick of every run and never fired).

| policy | F12 Z | miss rate | unfinished_at_cap |
|---|---|---|---|
| baseline | 2.4097 | 0.1066 | 30.43 |
| jsq | 2.0049 | 0.0058 | 0.00 |
| **ours** | **2.9498** | **0.2149** | **10.73** |
| **B3 (use_queue_term=False)** | **3.5278** | **0.2856** | **52.40** |
| use_reservation_False | 3.5319 | 0.2312 | 63.70 |
| use_priority_False | 2.9395 | 0.2240 | 8.37 |
| use_partial_False | 2.7075 | 0.3524 | 15.50 |
| ours_JIT | 2.9498 | 0.2149 | 10.73 |
| use_charge_time_term_False | 4.2954 | 0.4011 | 103.83 |

`ours` is **unchanged to 3-4 decimals** from the original (pre-fix) X3 run (Z=2.950, miss=0.215, unfin=10.7) — confirms the fix never touched the code path `ours` actually uses at default settings.

**B3 collapses from the best policy tested (0.000 miss rate, pre-fix) to one of the worst (0.2856, post-fix) — worse than plain `baseline` (0.1066) and far worse than `jsq` (0.0058).** Paired Wilcoxon (same 30 pairs as the original pre-registration): ours vs B3 on miss_rate, mean diff (ours−B3) = **−0.0707, p=0.032** (significant) — `ours` now has the *lower*, better miss rate, the opposite sign from the original pre-registered result. On F12 Z, mean diff = −0.578, p=0.452 (not significant, but same reversed direction: `ours`'s Z is now numerically better than B3's, not worse).

**`use_reservation_False` is now clearly the worst-behaving of the "removes one thing from ours" variants (0.2312 miss, 63.70 unfinished, worst Z besides `use_charge_time_term_False`)** — with the physical backstop now forcing genuinely-collided reservations into real `WAITING_FOR_PAD` delay instead of phantom concurrent charging, F9's removal produces exactly the real, measurable harm REMEDIATION.md's own description of F9 ("mandatory, prevents stampede") predicts. This is the first time `use_reservation`'s ablation has shown a real, non-null effect in this project.

**Conclusion: X3's original headline ("queue-awareness actively HURTS miss rate under scarce-station contention") is retracted.** It was entirely an artifact of B3 being allowed to violate pad capacity. The corrected picture is closer to the opposite: `ours` (queue-aware) now performs *significantly better* than B3 (not queue-aware) on the primary miss-rate metric in exactly the config where the original claim was strongest. `ours`'s own miss rate (0.2149) is real and not a capacity artifact (`ours` was never affected by the bug), so `density_scarce` remains a genuinely hard config for every policy tested — that part of the original finding (density_scarce is stressful) stands; what's retracted is specifically the "B3 beats everything, including `ours`" claim.

**Confirmation checked directly, per user request (2026-09-23): does `use_reservation_False` or `use_charge_time_term_False` still improve miss rate over default `ours`, post-fix? No — both are now WORSE, not better:**

| policy | miss rate |
|---|---|
| ours (default) | 0.2149 |
| use_reservation_False | 0.2312 |
| use_charge_time_term_False | **0.4011** (worst of all 9 policies) |
| use_priority_False | 0.2240 |
| use_partial_False | 0.3524 |

**This retracts more than just B3.** The original X3 root-cause diagnosis (Section 13, "Isolated by running the full ablation set in this config: turning off use_queue_term, use_reservation, or use_charge_time_term individually each independently drops miss rate to ~0.000") rested on THREE ablations, and it's now clear at least two of the three were capacity-bypass artifacts, not genuine fixes:
- `use_queue_term=False` = B3, already retracted above.
- `use_reservation_False` (with `use_queue_term=True`, the default) hits the **second** capacity bug found this session: without F9 updating `free_time`, `deterministic_wait` always sees every pad as permanently free (initialised once, never touched again), so this ablation was *also* silently allowing phantom concurrent charging — fixed by the same physical occupancy backstop. Post-fix it shows real, measurable harm (0.2312, worse than default), consistent with F9 actually mattering, not with it being safe to remove.
- `use_charge_time_term_False` sets `T_chg=0` not only in F8's ranking cost but also in the **reservation's own duration** (`T_chg` feeds `end = best_start + T_chg` for the `free_time` update at line ~747-749) — so disabling it made every reservation claim a **zero-duration** charging session for bookkeeping purposes, corrupting `free_time` for every subsequent reservation at that pad regardless of `use_reservation`'s setting. This is a third, related bookkeeping artifact (not yet a `ValueError`-guarded invalid combination, just a case where the ablation's own semantics leak into the wrong place) — the physical backstop now catches the resulting collisions and shows the true cost (0.4011, the worst of all 9 policies), rather than a silently wrong ~0.000.

Only `use_priority_False` (0.2240) and `use_partial_False` (0.3524, worse) were correctly diagnosed pre-fix as "doesn't fix it" — those two never touched `free_time` and are unaffected by either capacity bug.

**What survives from the original F8/F9 diagnosis chain:** the *initial* "ablation isolation" step above is retracted (built on two artifacts, not genuine fixes). The **subsequent, independent** priority-inversion diagnosis — the dose-response table correlating `ahead_lower_priority` with bad-mission rate, computed entirely from default `ours`'s own genuine (never-buggy) session data — did not rely on any of these three ablations and stands on its own evidence. The **bounded-lookahead F9 variant** (`f9_lookahead_cap_min`, a new deferral mechanism layered on default `ours`, never touching `use_reservation`/`use_queue_term`/`use_charge_time_term`) and its dramatic fix (0.2149→0.0013 in the original run) also stand, unaffected by this retraction — worth re-confirming at some point given how much else in this chain turned out to be wrong, but not invalidated by anything found so far.

### Post-fix, `ours` is the only policy showing a crossover (2026-09-23)

Across the corrected X4 grid: `baseline` and `jsq` show **no crossover** (concentrated wins at every load, as originally reported — both unaffected by the bug). Corrected `B3` also shows **no crossover** (concentrated wins at every load, reversed from its original "always wins" claim). Only `ours` shows a genuine crossover (distributed wins at low-moderate load, concentrated takes over from rate≈1.1). **This is the cleanest form this result has taken**: the one structural difference between `ours` and all three non-crossover policies is F8's queue term (`use_queue_term=True`, present only in `ours` among these four) — B3 is `ours` with that term off, and B3 shows no crossover either. The crossover is therefore attributable specifically to F8's queue-awareness, not to routing, reservations, priority, or partial charging in general (all of which B3 also has, and still shows no crossover).

### X4 full grid, re-run post-fix (2026-09-23) — B3's "distributed always wins" also reverses completely

`experiments/x4_layout_crossover.py`, identical grid (4 policies × 2 arms × 7 loads × 30 pairs = 1680 runs), 1555.3s. Raw: `results/x4_full_20260923_212821.csv`.

**`baseline`, `jsq`, `ours` rows are bit-identical to the original (pre-fix) X4 run** — confirms these three were never touched by the bug (none of them ever set `use_queue_term=False`). `ours`'s genuine crossover (distributed wins rate 0.3-0.9, concentrated takes over from rate≈1.1) stands exactly as originally reported.

**`B3` (`use_queue_term=False`) reverses completely — from "distributed always wins, flat ~1.01min" to "concentrated always wins, with real misses at high load":**

| rate | conc delay | dist delay | winner | dist miss rate |
|---|---|---|---|---|
| 0.3 | 1.34 | 1.63 | concentrated | 0.000 |
| 0.5 | 1.36 | 2.32 | concentrated | 0.000 |
| 0.7 | 1.36 | 3.61 | concentrated | 0.000 |
| 0.9 | 1.37 | 6.63 | concentrated | 0.075 |
| 1.1 | 1.41 | 10.45 | concentrated | 0.320 |
| 1.3 | 1.51 | 11.82 | concentrated | 0.518 |
| 1.6 | 2.01 | 12.41 | concentrated | 0.495 |

There is no load point at which corrected B3 prefers distributed — concentrated wins the delay comparison at every rate tested, and distributed's miss rate climbs to ~50% at high load (rate 1.3-1.6). B3 is now visibly *worse* than `ours` on distributed at every load ≥0.9, not better.

**The two attribution checks and `use_partial=False` (order-(c), conditional on "if X4 still leaves the question open") are not needed.** The premise those checks were investigating — "what makes B3 robust to distributed layouts, if not reservation/priority/partial-charging individually" — is dissolved: B3 is not robust to distributed layouts at all once pad capacity is correctly enforced. There is nothing left to attribute. The original "reservation-based deterministic scheduling (not partial charging) makes distributed layouts robust" narrative (Section above, X4 follow-up checks 1 and 3) is retracted in its entirety, not revised — it was built entirely on a capacity-violating B3.

**What survives:** `ours`'s own genuine crossover (queue-awareness, F8, present only in `ours`) is the one real, uncontaminated finding from this whole line of investigation. It was never B3's to begin with.

**Energy decomposition, per completed mission (mean of 30 pairs), all 7 configs — full table in `results/x5_full_20260923_164826.csv`; consistent pattern in every config:** partial/adaptive charging shows sharply higher `station_trip_energy/mission` than full charging in every single config and both policy families (e.g. `fleet_20_centre`: ours_partial 4.80 vs ours_full 1.19; baseline_adaptive 3.43 vs baseline_full 0.67), while `mission_flight_energy/mission` stays close across variants within a config (reflecting the same missions being flown). This is a direct, now precisely-measured confirmation of the mechanism first inferred indirectly in the original Phase 4/6 work (more frequent, shorter charge trips under partial/adaptive charging cost extra flight energy) — previously inferred from session counts, now measured directly via the new `station_trip_energy_wh` decomposition. `stored_charge_change/mission` is negative in every config/policy (fleet draws down net stored charge over the run relative to its start), with no anomalies.

**Status: X5 done.** H5 tested directly for the first time (previously only total energy — not makespan/miss rate — had been measured against full-vs-partial, which E12 flagged as not actually testing H5). Result: mixed, config-dependent, reported as-is.

## Checkpoint 7: E8/E9 fixes, MILP v2, X7 (2026-09-23)

**E9 (dwell-window truncation): found already correct, not a real bug.** `solve_charge_schedule_milp_ccv`'s C10 loop (`range(t, min(T, t + min_dwell_slots))`) already bounds by `T`. Verified directly: a drone needing exactly one slot in the final slot, with `min_dwell_slots=3` (would force 3 consecutive slots if untruncated, but only 1 is available), stays `Optimal`. Same pattern as E6 earlier in this project (checked, found already right, made permanent with a regression test rather than "fixed" for appearances) — `test_milp_v2.py::test_E9_dwell_window_already_truncated_at_horizon`.

**E8 (F13, exact within-slot CC-CV): a real bug, fixed.** `f13_pieces_for_band` (`sim/milp.py`) computes, for a drone starting a slot in band `l`, the exact piecewise-linear function Φ_l(S) = min_k(a_k·S + b_k) — one affine "regime" line per number of full band-boundaries crossed within the slot, derived analytically (regime 0: slope 1; regime m≥1: slope rate_{l+m}/rate_l, matching F13's own stated slope sequence) and a saturation-cap piece at 1.0. **Verified numerically against `soc_after_charging` to machine precision** (max abs error 2.2e-16) across 4 battery/dt combinations × all 3 bands × 300-point grids each, including multi-band-crossing regimes (`test_E8_f13_pieces_match_soc_after_charging_on_fine_grid`). Wired into `solve_charge_schedule_milp_ccv`'s C9 constraint, replacing the old single-rate-per-slot formulation. All 10 pre-existing `test_phase5_milp.py` tests still pass unchanged (244.7s, no regression), plus a new regression test (`test_E8_ccv_milp_uses_f13_and_does_not_overshoot_a_band`) pinned to E8's own described failure mode (dt=10min, battery=90Wh, starting at 69%).

**MILP v2 (`solve_charge_schedule_milp_v2`, `sim/milp.py`), REMEDIATION.md Section 4's real F12 objective, replacing v1's constant pad-slot-count objective.** Depot simplification (stated as in the paper): stations at a depot, missions start/end there, each mission = `{duration_slots, energy_wh (already includes travel), release_slot, deadline_min}`. Adds mission variables `u[i,k,t]`, flying-status exclusivity (A5), tardiness/makespan (`T_k`, `C_max`), reuses F13's band-indicator machinery for C9 and the (already-correct) C10 dwell logic. Objective: REMEDIATION Section 2's *raw* F12 form (`alpha*C_max + beta*energy_cost($) + gamma*sum(T_k)`, not `mission_sim.py`'s normalized reporting variant — different units, used intentionally since Section 4 says "Objective: F12" referring to the raw Section 2 definition).

**Addition 3 (solver time-limit rule):** `is_optimal = (status == "Optimal")` is returned explicitly; every gap computation downstream checks it first — a CBC time-limit stop is never silently treated as proof of optimality. (Retrieving a numeric best-bound from PuLP's `PULP_CBC_CMD` wrapper on timeout is not reliably available through this binding without extra stdout-parsing infrastructure not built here — not implemented; on a real timeout the script would report status/feasible-Z only, with gap left `None`, rather than fabricate a bound. Did not occur in the actual X7 run below — all 24 instances solved to proven optimality well inside their time limits.)

**Addition 4 (capacity invariant on the solution):** both `solve_charge_schedule_milp_v2` and `solve_charge_schedule_ours_v2` verify Σ_i x[i,j,t] ≤ pads[j] directly from the returned solution's `x` values, independent of solver status, raising `AssertionError` on any violation — the same discipline as the mission-simulator's own new hard invariant (Section 13, above). Never fired in this run.

**Addition 2 (discretised `ours` must be verifiably the same policy):** `solve_charge_schedule_ours_v2` imports and calls `sim/formulas.py`'s F6 (`target_soc`), F7 (`deterministic_wait`), F10 (`charging_slack`), F11 (`margin`, `combined_priority`) **directly** — the identical functions `sim/mission_sim.py`'s `policy='ours'` branch calls — not a second, independently-written implementation. The depot simplification collapses geometry to nothing (τ_ij=0, e_ij=0 for every station), so F5's gate trivially reduces to `soc>=sigma` and F8's cost reduces to `W_j + T_chg`; these reductions are algebraic consequences of the shared instance's geometry, not different logic.

**Real bug found and fixed while building the hand-checkable instance (2026-09-23):** the heuristic's charging-need trigger (borrowed from `mission_sim.py`'s open-ended engine, which always tops off an idle drone for a *next* mission that may arrive later) doesn't make sense for a MILP-comparison instance's *fixed, finite* mission list — a drone that just finished its only assigned mission kept re-triggering "top off to 1.0" for several pointless extra slots, since `s_req` falls back to `1.0-sigma` when no next mission is expected. Caught immediately via the hand-checkable instance (heuristic's first-pass `Z=64.3` vs the by-hand `42.7`, a suspiciously large, unexplained gap) — traced to `x_sol` showing charging sessions running past `T` itself. Fixed by gating the "needs charging" check on `any_work_remaining` (any mission still undone anywhere in the instance) OR a genuine safety violation (`S[i] < sigma`) — after the fix, the heuristic charges to the real story: F6's own `target_soc` floor (`recharge_trigger + 0.05 = 0.40`) makes it charge to 0.40 instead of the MILP's exact-minimum 0.30, a real, explained, modest (~6.3%) gap on the hand-checkable instance, not a bug.

**Hand-checkable instance (required by REMEDIATION.md Section 4): 2 drones, 1 station/1 pad, 2 missions, dt=10min, battery=90Wh, both start at S0=σ=0.20.** By hand: each mission needs 9Wh (0.10 SoC) beyond σ, so a drone must reach S=0.30 before departing; 1 pad forces sequential charging (drone0 slot 0, drone1 slot 1); drone0 finishes its mission at t=30min, drone1 at t=40min; Cmax=40min, 0 tardiness (deadline=60min), energy_cost=0.15×2×9Wh=2.7; **Z = 40+2.7+0 = 42.7.** MILP v2 reproduces this **exactly** (`test_milp_v2_hand_checkable_instance`). The heuristic on the same instance: Cmax matches (40, same schedule length), but Z=45.4 (energy=5.4, not 2.7) — a real, hand-explained ~6.3% gap from F6's floor, not a bug (`test_ours_v2_reuses_formulas_and_shows_a_real_nonzero_gap`).

**X7, complete (2026-09-23): `experiments/x7_milp_v2_gap.py`, 8 configs (n_drones=2..8, 1-3 stations) × 3 seeds = 24 instances, 20.6s total.** "Same instance" for v1 (addition 1): each instance has one canonical `{n_drones, pads, S0}`; v2 gets a drawn mission list; v1 (which has no mission concept) gets a *derived* `required_soc[i] = sigma + mean(mission energy)/battery_wh` and `deadline_slot` from the same `deadline_min` — the closest "same instance" can mean given v1's model literally cannot represent missions, documented in the script rather than silently assumed. Raw: `results/x7_milp_v2_gap_20260923_221122.csv`.

| | v1 (constant objective) | v2 (real F12 objective) |
|---|---|---|
| Optimal / 24 | 24/24 | 24/24 |
| mean gap | **0.0** (every single instance) | **0.714** (71.4%) |
| gap range | [0.0, 0.0] | [0.048, 1.517] |

**E10 directly confirmed: v1's historical 0% gap is a property of its constant pad-slot-count objective, not evidence the heuristic is near-optimal.** On the exact same 24 underlying instances (same drones, same pads, same charging demand), v1 shows 0% gap on all 24 while v2 shows a real, substantial, highly variable gap (4.8% to 152%, mean 71.4%). **Mechanism, not chased further given the scope of this checkpoint:** the hand-checkable instance isolated one real contributor (F6's conservative `target_soc` floor, ~6.3% there) but the much larger gaps at bigger instances (n≥4, gaps 60-150%) plausibly reflect the heuristic's *myopic, sequential* decision-making (charge-then-assign, one drone/mission at a time) against the MILP's *joint* global optimization over which drone flies which mission, when it charges, and to what target, all at once — a fundamentally different, and expected, source of suboptimality once the objective is no longer degenerate. Not verified component-by-component here; a natural next increment, not done in this pass.

**Status: checkpoint 7 done.** `pytest -q` → **87 passed** (81 + 6 new: 5 in `test_milp_v2.py`, 1 elsewhere), 338.2s, zero regressions across the full suite (Phase 1-5, MILP v1/ccv/v2, all remediation-era regression tests).

### X7's 71.4% mean gap, explained (2026-09-23)

**1. Per-term decomposition of the gap, all 24 instances.** Ratio-per-term is unstable (MILP's own energy term is sometimes near-zero, blowing up the ratio) — used **absolute contribution to the Z gap** instead: `tardy` contributes **exactly 0 in all 24 instances** (`milp_tardy == heur_tardy == 0.0` everywhere — the generated deadlines, 100min, were generous enough that neither solver is ever late, so there is no volatility to report from a near-zero tardiness denominator; the gap simply isn't there). The gap splits between **makespan (mean 44.7% of the absolute Z gap) and energy cost (mean 55.3%)** — `d_cmax` is always a clean multiple of `dt_min=10` (0, 10, or 20 minutes), a discrete scheduling-delay signature, not noise. Gap correlates positively with instance size (`corr(gap, n_drones) = 0.51`) and with pad contention (`corr(gap, drones_per_pad) = 0.32`) — the gap grows with both, as expected for a heuristic against joint optimization. Full breakdown: `results/x7_term_decomposition.csv`.

**2. Rolling-horizon hypothesis tested directly — does not hold, for a structural reason.** Every X7 instance has `release_slot=0` for every mission, so the heuristic already has full knowledge of the entire mission list from t=0 — there is no literal future-information gap to close. Tested the next-best form of "oracle": a `oracle_assignment=True` flag on `solve_charge_schedule_ours_v2` that replaces the greedy earliest-deadline/first-idle-drone pairing with a **one-shot globally-optimal bipartite assignment** (Hungarian algorithm via `scipy.optimize.linear_sum_assignment`, minimizing charging shortfall per drone-mission pair), computed once at t=0 from the same full mission list the greedy version already sees. Result: **mean gap drops only modestly, from 71.4% to 65.1%, and the direction is inconsistent instance-by-instance** (13/24 improve, the rest are unchanged or *worse* — e.g. n=4/st=2/seed=1: 18.8%→74.3%). **The rolling-horizon/information-availability explanation is directly refuted (information was never missing); a naively-better one-shot pairing rule is not the answer either** — the static cost matrix doesn't account for the dynamic charging/pad-contention schedule that emerges over time, so forcing a "globally optimal" pairing based on a snapshot can produce worse timing than the adaptive greedy version. This points at something the MILP does that no simple one-shot pairing fix can replicate — see point 3.

**3. Worst instance (n=8, 3 stations, seed=3, gap=149.0%) inspected directly.** MILP: `Cmax=20min` (2 slots) — achieved by **reusing a small number of drones for multiple missions back-to-back within the same tight window** (e.g. drone 0 flies mission 7 at slot 0, then immediately mission 2 at slot 1, both within the 2-slot Cmax), packing 8 missions onto fewer effective drone-slots. Heuristic: `Cmax=40min` (4 slots) — its greedy, one-mission-at-a-time-among-currently-idle-drones assignment spreads the 8 missions across more drones without this back-to-back reuse, and charging queues up more sequentially at the 3 pads (one drone even charges twice, at slots 0 and 2) rather than the MILP's tightly interleaved joint schedule. **In one sentence: the MILP jointly co-optimizes which drone flies which mission, when, and how much each charges, all at once, including reusing a drone for a second mission the instant it's free; the heuristic decides drone-mission pairing and charging amount separately and greedily, one epoch at a time, and never revisits an earlier decision once made.**

**Conclusion:** the 71.4% mean gap is real, is not concentrated in tardiness (which never binds in these instances), is not primarily an information/rolling-horizon artifact (ruled out directly), and is not resolved by a smarter one-shot assignment rule alone. It is consistent with the genuine, expected difference between an exact joint optimizer and a fast, greedy, non-backtracking heuristic — exactly the kind of gap X7 exists to measure once the objective isn't degenerate (E10). Not chased further into a full explanation of every instance; the mechanism is identified and reproducible, not exhaustively decomposed drone-by-drone.

**4. Regime check: X7's headline 71.4% was measured where the deadline constraint never binds — not the regime `ours` is designed for.** Every one of X7's 24 instances used `deadline_min=100` (10 slots) against missions needing at most 2 slots to fly plus ~1 to charge — generous enough that `milp_tardy == heur_tardy == 0.0` in all 24 (confirmed directly in point 1 above). `experiments/x7_tight_deadline_gap.py` re-runs the exact same 24 instances (same configs, same seeds, same station/S0/mission draws) with `deadline_min=25, horizon_min=50` — tight enough that the deadline constraint binds for at least one solver in **20/24 instances** (`results/x7_tight_deadline_gap_20260923_230719.csv`, 14.0s).

| | non-binding-deadline (original X7) | tightened-deadline (this follow-up) |
|---|---|---|
| v1 mean gap | 0.0% (24/24) | **0.0% (24/24) — unaffected** |
| v2 mean gap | 71.4% | **109.2%** |
| v2 gap range | [4.8%, 152%] | [4.2%, 309%] |

**The gap does not shrink once deadlines actually bind — it grows.** v1's gap stays exactly 0% (confirms E10 again, independent of the deadline regime — v1's model doesn't have a mission/deadline concept to begin with, so tightening deadline_min can't touch it). v2's mean gap rises to 109.2%, with the top of the range reaching 309%. **Read together with X7's own point 3 (the worst-instance mechanism): once deadlines genuinely bind, the heuristic's greedy, non-backtracking, one-epoch-at-a-time decisions have even less room to recover from an early suboptimal pairing before a deadline is missed — exactly the direction the joint-vs-sequential mechanism predicts.** Framed the way the user asked: **the X7 headline gap comes from non-binding-deadline instances either way** — the tightened variant does not show a smaller, "more representative" gap once deadlines matter; if anything the opposite. H6 above is written against the fuller picture (both regimes), not just the original 71.4% figure.

## Checkpoint 8: X8, weight sensitivity (2026-09-23)

`experiments/x8_weight_sensitivity.py`, `policy='ours'`, 2 configs (`density_scarce`, `load_saturated` — the two X3 configs with genuine contention/nonzero miss rates; every other X3 config saturates near 0 miss for every policy, leaving no signal to sense weight changes against), 4 w1/w2 combos × 15 (layout, seed) pairs = 120 runs, 173.5s. Weights not selected to favour any hypothesis — symmetric grid around the existing default (1,1)/(1,1,1). alpha/beta/gamma computed **post hoc from the same runs** (confirmed directly from the code: alpha/beta/gamma only ever feed `objective_F12`'s final Z, never a dispatch decision — no extra simulation needed to sweep them). Raw: `results/x8_weight_sensitivity_20260923_225639.csv`.

**w1/w2 sensitivity (F11 priority weights), mean of 15 pairs:**

| config | w1=1,w2=1 | w1=2,w2=1 | w1=1,w2=2 | w1=0.5,w2=0.5 |
|---|---|---|---|---|
| density_scarce (miss rate) | 0.2155 | 0.2109 | 0.2099 | **0.2155 (identical to 1,1)** |
| load_saturated (miss rate) | 0.0841 | 0.0774 | **0.0657** | **0.0841 (identical to 1,1)** |

**(0.5, 0.5) is bit-identical to (1, 1) in both configs, and this is structural, not coincidental**: `combined_priority`'s ranking only depends on the *relative* ordering it produces, and scaling both w1 and w2 by the same factor scales every drone's priority score uniformly, changing no ranking (the `+inf` feasibility-emergency branch is unaffected by scaling too) — **uniformly scaling both weights together can never change `ours`'s scheduling decisions**, a useful, previously-undocumented structural fact about F11, now worth recording.

Within the tested grid, weight choice moves miss rate only modestly at `density_scarce` (0.2099–0.2155, <1pp range) but more at `load_saturated` (0.0657–0.0841, margin-weighted `w1=1,w2=2` gives a ~22% relative reduction vs the current default). **Not a large enough or clean enough effect to justify changing the project's default** (a single reduced-scope 15-pair sweep, not the ≥30-pair rigor this project requires before treating a result as final) — reported as an observation for a future, properly-powered follow-up, not acted on here, per X8's own instruction not to select weights to favour a hypothesis.

**alpha/beta/gamma sensitivity: does a different F12 objective weighting favour a different w1/w2 choice?** Computed Z under 4 weightings (default (1,1,1), C_max-heavy (2,1,1), energy-heavy (1,2,1), tardiness-heavy (1,1,2)) for every w1/w2 combo already run. **The best-scoring w1/w2 is stable within each config across all 4 objective weightings tested** — `density_scarce` always prefers `(1,1)` (tied with `(0.5,0.5)`); `load_saturated` always prefers `(1,2)`, never reversing regardless of which F12 term is emphasized. No hypothesis-dependent flip-flopping was found in this grid.

**Status: checkpoint 8 done.** Findings: (1) uniform w1/w2 scaling is a documented no-op; (2) weight choice has a real but modest effect, more visible under saturated load than scarce-station contention; (3) the best w1/w2 choice (where one exists) does not depend on which F12 term is emphasized, in every combination tested. Not a large enough effect, nor a properly-powered sweep, to justify revising the project's w1=w2=1 default.

## Final write-up (REMEDIATION.md Section 8, 2026-09-23)

REMEDIATION.md's checkpoint list (Section 9) is now complete through checkpoint 8. This section is the required close-out: headline results as they now stand, every invalidated result marked with the bug that caused it (not deleted), and every open item stated plainly. The Section 9 hypothesis table above now carries a `Status (2026-09-23)` column for H1-H6 individually — this section is the narrative summary.

### Headline results, as they now stand

1. **`ours` is the only one of the four primary policies showing a genuine layout crossover, attributable specifically to F8's queue term.** Across X4's corrected full grid (post pad-capacity fix), `baseline`, `jsq`, and `B3` (`ours` with `use_queue_term=False`) all show concentrated winning at every load tested — no crossover for any of the three. Only `ours` (queue-term on) shows the crossover (distributed wins at low-moderate load, concentrated takes over from rate≈1.1). Since `ours` and `B3` differ by exactly that one flag, this is the cleanest attribution this project has produced: **the crossover is F8's, not routing, not reservations, not priority, not partial charging.**
2. **F7's deterministic waiting-time prediction is exact at full scale.** X6, reusing X3's already-logged `prediction_error_min` field: 154,726 completed sessions across all 5 X3 configs, **154,726 exact matches, 0 nonzero** — the project's central claim (a scheduled system's wait is computable, not merely estimable) holds with no exceptions found.
3. **The v1-vs-v2 MILP comparison settles E10.** Run side by side on the exact same 24 instances: v1 (the historical, constant-objective MILP) shows 0% gap on all 24, in *both* the original and the tightened-deadline regime — confirming this was always a property of v1's degenerate objective, never evidence the heuristic was near-optimal. v2 (the real F12 objective) shows a real, substantial gap: 71.4% mean where deadlines never bind, rising to 109.2% where they do. H6 ("within a few percent") is refuted, not narrowly missed.

### Every invalidated result, marked with its cause (not deleted)

| Bug | What it invalidated | Status |
|---|---|---|
| **Pad-capacity bug** — `time_to_ready_cost`'s `use_queue_term=False` branch (B3's defining flag) set `start = t_arr` unconditionally, ignoring the chosen pad's actual free time. Verified: up to 5 UAVs "charging" concurrently at one physical pad. | X3's `density_scarce` B3 result (0.000 miss rate — the project's original headline "queue-awareness hurts" claim); X4's B3 row ("distributed always wins, flat ~1.01min"); the X4-followup `B3+use_partial=False` check; both `B3_no_reservation`/`B3_no_priority` attribution runs; the entire "reservation-based deterministic scheduling makes distributed layouts robust" narrative built on these. | **Fixed 2026-09-23.** `density_scarce` and X4's full grid re-run and corrected (Section 13 above). The other B3-bearing checks were not individually re-run — see open items below. |
| **Per-pad vs whole-hub metric (E1)** — Table 2's `L_d` (Eq. 11) is one distributed queue's length, with no dependence on `n`; the pre-remediation Phase 3 "crossover shift" claim compared it directly against `L_c` (the whole concentrated hub's length) — not like-for-like, and at ρ=0.8,n=5,m=7 the two framings give opposite winners. | Phase 3's original "R3a shifts the crossover left by ~0.11-0.13" headline (`HISTORY.md`) and everything built on the L-metric before this was caught. | **Fixed conceptually 2026-09-22** — replaced by X1's like-for-like per-drone wait-time (`t`) crossover analysis, which found the *opposite* result (R3a loses to pooling, not beats it) once corrected. |
| **C9 band-rate error (E8/F13)** — `solve_charge_schedule_milp_ccv` applied a charging slot's *starting* band rate for the whole slot, even when the slot's charging genuinely crossed into a slower band partway through; verified capable of adding ~37% SoC in one 10-minute slot, an unphysical overshoot. Silently wrong output, not a crash. | Any `solve_charge_schedule_milp_ccv` result where a drone's charging crosses a CC-CV band boundary mid-slot. (The pre-existing hand-checked Phase 5 test instances happened not to trigger this — none of their scenarios crossed a band boundary within one slot — so their numbers were coincidentally still correct, not because the bug wasn't real.) | **Fixed 2026-09-23** with F13's exact within-slot pieces, verified to machine precision against `soc_after_charging`. |
| **F7/F9 tick-quantization bug** — F7/F9 computed reservation predictions from raw continuous travel/charge time, but the mission simulator can only register a state change at a tick boundary — a continuous prediction systematically understated the tick the engine would actually land on. | The original (pre-fix) deterministic-prediction test's "812/812 within 1 tick" result, which was masking a real, systematic +1-tick bias on 252/812 (31%) of sessions. | **Fixed 2026-09-22** (`_ceil_to_tick`). Test tightened from a 1-tick tolerance to an exact match; 794/794 exact post-fix, and X6 confirms 154,726/154,726 exact at full scale. |

*(Two smaller, earlier-caught issues from the same review round — the (10,9)-vs-(4,6) Table 3 transcription bug and the total-queue-crossover bisection-bracket bug, both in X1's analysis layer — are recorded in full in the checkpoint-3 log above; not repeated here since the user's list of four covers the ones with the largest downstream impact.)*

### Open items, stated plainly

- **B3's component-level attribution is still unresolved, and now doubly so.** Before the capacity fix, `B3_no_reservation`, `B3_no_priority`, and `B3+use_partial=False` all showed "removing this one component doesn't change B3's behaviour" — but all three of those checks were run on a **capacity-violating B3**, so that conclusion is itself contaminated by the same bug and has not been re-verified against the corrected code. Since the fix, B3 no longer shows the robust-distributed-layout behaviour those checks were trying to explain in the first place — the original question ("what makes B3 robust to distributed layouts") is moot, but a new, unasked one is open: B3 is now mostly *worse* than baseline (X3's `density_scarce`: B3 miss=0.2856 vs baseline 0.1066) — **why B3 underperforms plain baseline post-fix has not been investigated at all.**
- **F13/MILP v2 and the mission simulator are not connected.** F13's exact within-slot CC-CV pieces exist only inside `sim/milp.py`'s two MILP formulations (v1-ccv and v2); `sim/mission_sim.py`'s own charging model is a genuinely continuous-time engine (`soc_after_charging`, ticked at `DT_MIN=1min`), never discretized into F13's slot-and-band-indicator form, so there is no direct numerical cross-check between the two. Separately, `solve_charge_schedule_ours_v2` (the MILP-comparison heuristic) is **not** `sim/mission_sim.py`'s `run_mission_sim(policy='ours')` — it's a smaller, depot-abstracted reimplementation of the same epoch-loop *shape* that reuses the same F6/F7/F10/F11 *functions*. The "verifiably the same policy" claim (addition 2, checkpoint 7) is true at the level of shared formulas, not a single shared execution engine across the mission simulator and the MILP harness — a real, documented scope boundary, not an oversight.
- **The flat energy model (κ=0.01 Wh/m) remains the only genuinely open Section 7 decision.** The fuller `P(v,m)` power model is coded behind the `ENERGY_MODEL` switch in `sim/energy.py` but has never been calibrated — it needs real flight data from the hardware track (Section 14.8), which has not started.
- **Hardware track: not started.** Still Phase H0 (component list and v1 scope only, Section 14) — the user directed this session to the simulation track exclusively; no schematic, design review, or hardware code exists.
- **R3b/R3a's queue-only-model results are not at full statistical rigor across the whole (n,m) grid.** Only 3 representative points (grid corners + middle) were brought to 30-seed rigor; the full 28-point grid was confirmed computationally infeasible in one sitting (~27h extrapolated) and was never revisited after remediation began.
- **No tariff-aware charging policy exists.** Phase 6's time-of-use tariff experiment (`HISTORY.md`) flagged its own horizon as not reaching peak pricing hours; X8 did not touch the tariff dimension either. Neither policy family (`baseline`, `ours`) shifts charging timing to chase cheaper electricity.
- *(Resolved, no longer open, noted for completeness: Phase 5's "re-measure the optimality gap against the CC-CV MILP" item from `HISTORY.md` is now superseded by X7, which measures the CC-CV/mission-aware MILP's gap directly — the natural next step `HISTORY.md` flagged has been done.)*

---

## 14. Hardware track: charging pad prototype

**Note (2026-09-21): the user has directed this session to focus on the simulation track only. This section is retained as project reference but is not being actively worked on.**

### 14.1 Purpose and relationship to the simulation track

A single physical charging pad is built to ground the simulation in real measurements. It is **not** used to fly the full schedule with a fleet. It provides three things for the paper:

1. **Measured CC–CV charging curves** → fit the piecewise-linear segments (a_ℓ, b_ℓ) used in the model (Section 4.3), replacing the assumed three-band table.
2. **Measured energy** → calibrate β0–β3 of the flight power model and the charging efficiency η.
3. **Measured time-to-ready (`eta_ready`)** → check the deterministic waiting-time prediction W_j (Section 5.2) against hardware.

The two tracks are independent until hardware Phase 8. Hardware Phases 1–5 need no flying and can run in parallel with simulation Phases 3–6.

**Status: hardware Phase 0.** Components have been listed and a v1 scope agreed in principle, but the three core design decisions (14.2) are not finalised, and there is no schematic, design review, or order yet.

### 14.2 The three core design decisions (open)

**D1. How charge is transferred.**

| Method | Pros | Cons | Status |
|---|---|---|---|
| Conductive contact plates | Cheap, high power, simple | Needs alignment; contacts oxidise; polarity problem | **Recommended for v1** |
| Inductive / wireless | No exposed contacts, tolerant to yaw | ~70–85% efficient, coil alignment matters, costly | Possible v2 |
| Battery swap | Fastest turnaround | Mechanically complex | Out of scope for v1 |

**D2. Polarity.** A drone lands at an arbitrary yaw angle, so flat plates risk reversed polarity. Options:
- **Concentric ring electrodes (recommended):** inner disc = +, outer ring = −; landing-gear contacts at two different radii, so orientation does not matter.
- Bridge rectifier on the drone: polarity-agnostic but loses ~0.6 V and produces heat.

**D3. Where battery management lives.**
- Smart battery with onboard BMS: pad only supplies regulated DC.
- Bare LiPo pack: pad must do CC–CV **and** per-cell balancing via the balance lead. More work, but much better telemetry for research.

### 14.3 Agreed v1 scope

Single pad; concentric ring electrodes; passive 3D-printed funnel for alignment (no actuators in v1); load cells + microswitches for landing detection with two-sensor agreement; ESP32-S3 with MQTT over WiFi; OLED display and LED ring; hobby CC–CV charge module; INA226 current/voltage sensing; microSD logging; full safety set. Actuated centring and a weather cover are deferred until v1 works.

### 14.4 Components by subsystem

**Power input and conversion**

| Component | Suggested part | Notes |
|---|---|---|
| AC–DC supply | 24 V, 10–15 A (Mean Well class) | Sized for peak charge current × pads |
| Buck converter | XL4015 (5 A) or LM2596 (3 A) | Steps down to charger input |
| Logic rail | AMS1117 3.3 V / 5 V | Separate from the charge path |
| Reverse-polarity protection | P-MOSFET ideal diode | |
| Fusing | Blade fuse + PTC resettable | One per pad |
| TVS / snubber | SMBJ series | Protects against inductive spikes |

**Charging and battery management**

| Component | Suggested part | Notes |
|---|---|---|
| CC–CV controller | iMAX-B6-class module (v1) or BQ25730/BQ2589x | Module is faster to get working |
| BMS (bare cells) | Daly 3S/4S or HX-3S-01 | Must balance cells |
| Current/voltage sensing | **INA226** (I²C) | Primary energy measurement for research |
| Coulomb counter | MAX17043 / LTC2941 | Better SoC than voltage alone |
| Pad switch | High-side MOSFET or SSR | Never a mechanical relay for DC under load |
| Battery temperature | **MLX90614** (non-contact IR) or DS18B20 | |

**Landing detection** (at least two methods must agree before charging starts)

| Sensor | Part | Detects |
|---|---|---|
| Load cells + HX711 | 4× 5 kg cells at pad corners | Weight; also gives payload mass m for the power model and centre of mass for alignment |
| Microswitches | SPDT lever switches | Physical contact |
| Time-of-flight | VL53L0X / VL53L1X | Approach before touchdown |
| IR beam-break | TCRT5000 | Pad occupied |
| Hall effect + magnet | A3144 + magnet on skid | Correct seating |
| Contact continuity | Resistance across electrodes | Real electrical contact, not just presence |

**Alignment and actuation**

| Component | Notes |
|---|---|
| Passive funnel / V-grooves | 3D printed; v1 uses this only |
| Centring arms (v2) | NEMA 17 + DRV8825, or MG996R servos, with endstops |
| Weather cover (v2) | Linear actuator, 100–150 mm stroke |
| Precision landing aid | ArUco/AprilTag + downward camera, or IR-LOCK beacon |

**Control and communications**

| Component | Suggested part | Notes |
|---|---|---|
| Main MCU | **ESP32-S3** (or Pico W) | WiFi, BLE, I²C, ADCs |
| Messaging | MQTT via Mosquitto broker | Suits a multi-pad fleet |
| Drone link | MAVLink over telemetry radio or WiFi | Land commands, battery telemetry |
| Real-time clock | DS3231 | Timestamps; tariff-aware scheduling |
| Storage | microSD module | Log every charge session |
| Optional host | Raspberry Pi 4 | ROS 2 and camera-based landing |

**Display and user interface:** SSD1306 1.3" OLED (or 3.5" TFT); WS2812B LED ring (colours for idle / charging / reserved / fault); active piezo buzzer; manual override buttons.

**Safety (mandatory, not optional):**

| Component | Purpose |
|---|---|
| Hardware emergency stop | Cuts the charge path directly, not through software |
| Thermal fuse / cutoff | Works even if firmware hangs |
| Smoke detector | Output wired to an MCU interrupt |
| LiPo-safe enclosure or bag | Containment during testing |
| Watchdog timer | Stops charging if the firmware loop stops |
| Over/under-voltage lockout | Refuses to charge a damaged pack |
| Hardware current limit | Cannot be overridden by a firmware bug |

**Mechanical and environmental:** aluminium pad plate (or 3D print + copper tape for early tests); gold- or nickel-plated contacts (bare copper oxidises); IP65 enclosure for electronics if outdoors; 40 mm fan + heatsinks; BME280/DHT22 for ambient conditions (Li-ion should charge only within ~0–45 °C); anti-vibration mounts for load cells.

### 14.5 MQTT interface (pad → scheduler)

```
pad/{id}/occupied      bool
pad/{id}/uav_id        string
pad/{id}/soc           float  (0-1)
pad/{id}/power_w       float
pad/{id}/energy_wh     float  (energy delivered this session)
pad/{id}/eta_ready     float  (seconds until mission-ready; measured W_j)
pad/{id}/temp_c        float
pad/{id}/state         enum   (IDLE, DETECTED, VERIFYING, CHARGING, COMPLETE, RELEASED, FAULT)
pad/{id}/fault         enum   (NONE, OVERTEMP, OVERCURRENT, ESTOP, SENSOR_FAIL, CONTACT_LOST, ...)
```
Commands (scheduler → pad), suggested:
```
pad/{id}/cmd/reserve     {uav_id, target_soc}
pad/{id}/cmd/release     {}
pad/{id}/cmd/set_target  {target_soc}
```
Use retained messages for `state` and a last-will message that sets `state` to FAULT/offline if the pad disconnects.

### 14.6 Firmware state machine

```
IDLE --(two sensors agree: drone present)--> DETECTED
DETECTED --(contact continuity OK)--> VERIFYING
VERIFYING --(voltage/temp/pack checks pass)--> CHARGING
CHARGING --(target SoC reached or CV cutoff)--> COMPLETE
COMPLETE --(drone lifted)--> RELEASED --> IDLE
ANY STATE --(e-stop, overtemp, overcurrent, sensor fail,
             contact lost, watchdog, smoke)--> FAULT
FAULT --(manual reset only)--> IDLE
```
FAULT always de-energises the pad. Leaving FAULT requires a physical/manual reset, never an automatic or remote one.

### 14.7 Hardware development phases

Rule: do not start a phase until the previous phase's pass gate is met.

**Phase H0 — Design and safety planning** *(current)*
- Build: settle D1–D3; schematic; block diagram; one-page LiPo risk assessment (location, containment, who is present).
- Test: design review with supervisor or lab technician, focusing on the power path.
- Gate: schematic reviewed, BOM ordered, safe test location agreed.

**Phase H1 — Power bench (no battery)**
- Build: PSU, buck converter, logic rail, fuses, reverse-polarity protection, MOSFET pad switch.
- Test: load with power resistors or an electronic load; measure rail stability; deliberately trigger the fuse; reverse the input; measure converter temperature after 30 min at full current.
- Gate: stable rails, protections verified by actually triggering them, temperatures within ratings.

**Phase H2 — Charging and measurement**
- Build: charge module, INA226, temperature sensor, microSD logging.
- Test: dummy load first, then a small pack, supervised, in a LiPo bag. Log voltage, current, temperature through full charges. Confirm CC phase, CV switch, termination at the correct cutoff current. Cross-check INA226 against a multimeter.
- Gate: correct CC–CV profile and termination; pack temperature within limits; measurements within a few percent of the reference meter.
- Research output: the logged curve is used to fit the piecewise-linear segments.

**Phase H3 — Landing detection**
- Build: load cells + HX711, microswitches, two-sensor agreement logic.
- Test: calibrate with known weights; 50+ placement trials with a dummy mass (gentle, dropped a few cm, off-centre) plus false events (hand pressing a corner, fan blowing across).
- Gate: zero false charge-starts in all trials; mass accurate enough to use as payload m.

**Phase H4 — Electrodes and mechanical alignment**
- Build: concentric ring electrodes, landing-gear contacts, passive funnel.
- Test: 50+ hand placements at random yaw and offset; measure contact resistance each time; repeat after several days for oxidation.
- Gate: reliable contact at any yaw within the funnel's capture radius; consistently low contact resistance. Record the capture radius (precision landing must beat it).

**Phase H5 — Firmware state machine and safety interlocks**
- Build: state machine (14.6); OLED and LEDs show the current state.
- Test (fault injection): unplug a sensor mid-charge; warm the temperature sensor; press the e-stop; force a firmware hang to test the watchdog; lift the drone mid-charge.
- Gate: every fault ends de-energised; hardware protections work even with firmware deliberately broken.

**Phase H6 — Communications and ground station**
- Build: MQTT topics (14.5), broker, simple dashboard.
- Test: measure latency; kill WiFi mid-charge; restart the broker; send malformed commands.
- Gate: network loss never creates an unsafe state; pad resynchronises without manual reset (except from FAULT).

**Phase H7 — Integration with a real drone**
- Test: manual landings, then autonomous precision landing (ArUco/AprilTag or IR-LOCK). Full cycles: land → detect → verify → charge → report → release → take off. Then back-to-back soak tests, logging every failure.
- Gate: target success rate over consecutive autonomous cycles (e.g., 20 in a row), every failure logged and explained.
- Note: this phase usually takes longest. If time is short, Phase H8 data can mostly be collected with hand-placed landings.

**Phase H8 — Research data collection**
- Charging curve: fit (a_ℓ, b_ℓ) segments; report the approximation error of the piecewise-linear model.
- Charging efficiency η: energy drawn from the supply vs energy stored in the pack.
- Energy model calibration: fly known trajectories at set speeds v and payloads m; energy replaced on the pad (divided by η) = energy consumed in flight; fit β0–β3 by least squares with confidence intervals.
- Queue validation: compare measured `eta_ready` with the model's predicted W_j and charging time T^chg.

### 14.8 Code to be written for the hardware track

**Firmware (ESP32, C++, PlatformIO + Arduino framework or ESP-IDF):**
```
firmware/
  src/
    main.cpp            # setup, main loop, watchdog feed
    state_machine.cpp   # states and transitions from 14.6
    sensors.cpp         # HX711, INA226, MLX90614, switches, continuity
    charging.cpp        # pad switch control, target SoC, termination
    safety.cpp          # fault detection; FAULT entry; e-stop interrupt
    comms.cpp           # WiFi, MQTT publish/subscribe, last will
    display.cpp         # OLED + LED ring
    logging.cpp         # microSD CSV logging with RTC timestamps
  include/config.h      # pins, thresholds, calibration constants
```
Firmware rules:
- Safety checks run every loop iteration and cannot be disabled by configuration or MQTT command.
- Non-blocking code (no long `delay()`), so the watchdog and safety checks always run.
- All thresholds in `config.h` with units in names (e.g., `MAX_PACK_TEMP_C`).
- Log at a fixed rate (e.g., 1 Hz) to CSV: timestamp, state, V, I, P, energy_wh, soc, pack_temp_c, ambient_temp_c, mass_g, fault.

**Ground station and analysis (Python):**
```
ground/
  mqtt_logger.py        # subscribes to pad/#, writes CSV
  dashboard.py          # live view of pad states
  fit_charge_curve.py   # H8: fit piecewise-linear segments from logs
  fit_efficiency.py     # H8: estimate η
  fit_energy_model.py   # H8: least-squares fit of β0-β3 with CIs
  validate_wait.py      # H8: measured eta_ready vs predicted W_j
```
Outputs of the fitting scripts (charging segments, η, β0–β3) are written to a parameter file that the simulator's `sim/energy.py` loads, so calibrated values replace assumed ones without code changes.

**Optional later — hardware-in-the-loop bridge:** a Python adapter that lets the Phase 3+ scheduler send `cmd/reserve` messages to the real pad and read its state, so one real pad can sit among simulated pads.

### 14.9 Hardware figures for the paper

| Figure | Content |
|---|---|
| H-1 | Photo / diagram of the pad and subsystems |
| H-2 | Measured CC–CV curve vs fitted piecewise-linear model |
| H-3 | Energy model fit: measured vs predicted flight energy |
| H-4 | Measured `eta_ready` vs predicted W_j + T^chg |

### 14.10 Hardware open decisions

1. D1–D3 (Section 14.2).
2. Drone platform and battery type (cell count, capacity, connector).
3. Charging current and supply sizing.
4. Precision landing method (ArUco/AprilTag vs IR-LOCK).
5. Indoor-only or outdoor operation (affects enclosure and weather cover).

---

## 15. Rules for the Claude agent

1. **Never fabricate results, numbers, or figures.** Only report numbers from code you ran, with the real output. If something has not been run, say so. Expected values are hypotheses (Section 9), not outputs.
2. **Never tune code or parameters to make results match a hypothesis.**
3. Reuse the validated Phase 1/2 functions; do not silently rewrite them.
4. Every new phase must include its sanity checks and tests, and you must run them and see them pass before running experiments. Never weaken a test or loosen a tolerance to make it pass without telling the user why.
5. Change one assumption at a time; if a request would change two, point this out.
6. When an open decision (Section 13) affects the code, ask the user before writing that code. Record the answer in Section 13.
7. Keep notation consistent with Section 4.2.
8. Write clear, commented, modular code following Section 11.
9. When unsure about the reference paper's details, rely on Section 3; if still unsure, ask.
10. **Hardware safety:** never write firmware that can disable, bypass, or remotely reset safety interlocks, and never suggest skipping a hardware phase gate. Charging tests with LiPo packs must always be supervised and contained.
11. For hardware code, state which parts are untested on real hardware. Pin numbers and calibration constants must come from `config.h`, and you should ask the user for their actual wiring rather than guessing.
12. Do not delete or overwrite files in `results/`, `phase1_baseline.py`, or this file's history of validated numbers without explicit permission.
13. Do not launch long-running jobs (more than ~10 minutes) without first reporting the estimated runtime and getting the user's go-ahead.
