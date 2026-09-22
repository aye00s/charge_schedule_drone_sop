# REMEDIATION.md — Implementing Our Method Correctly

> **To Claude Code:** Save this file at the repository root next to `CLAUDE.md`, and add one line to `CLAUDE.md` Section 13: *"Active work: follow REMEDIATION.md."* All rules in `CLAUDE.md` Sections 0 and 15 still apply (tests first, report real output only, never tune to match a hypothesis, ask before long runs, never delete `results/`).
>
> **Why this file exists.** A review of the Phase 1–6 work found two kinds of problem:
> 1. **Our proposed method was never implemented.** The simulations used the reference paper's formulas, JSQ routing, and a partial-charging policy, but not the formulas that make up this project's contribution (deterministic waiting time, time-to-ready cost, reservation update, combined priority, our objective, the full heuristic). Section 2 of this file is the authoritative specification of those formulas.
> 2. **Several implementation and reasoning errors** in the existing code and write-up (Section 1).
>
> **Before writing any code:** read this whole file, run `pytest -q` to record the starting state, then ask the user the open decisions in Section 7. Propose a plan and wait for approval.

---

## Conventions for this file

- Time in **minutes**, simulation step Δt = 1 min (Phase 4 simulator). Energy in **Wh**, power in **W**, distance in **m**, speed in **m/s**, SoC as a fraction in [0, 1].
- Energy added in one charging step: η · r · Δt / 60 (Wh), because r is in W and Δt in minutes.
- Symbols follow `CLAUDE.md` Section 4.2. New symbols are defined where they first appear.

---

## 1. Errors to fix in existing code and write-up

Fix these before implementing Section 2, because several of the new experiments reuse this code. Each fix needs a test that fails before the fix and passes after it.

| ID | Where | Problem | Required fix | Test |
|---|---|---|---|---|
| E1 | Phase 3 crossover metric | L_d (Eq. 11) is **one pad's** queue; L_c (Eq. 13) is the **whole hub's** queue. At ρ=0.8, n=5, m=7: distributed total = n·L_d ≈ 8.1 vs hub 2.2, yet the metric says distributed is better. The queue-length crossover is not a like-for-like comparison. | Make the **primary** crossover the per-drone waiting time t (already like-for-like, since t_d = n·L_d/(1−P_b)). Also report the **total** queue crossover (n·L_d vs L_c) and blocking probability. Keep the per-pad crossover only as "replication of the reference metric." | Assert t_d_analytic ≈ n·L_d/(1−P_b) at several ρ. Assert the per-drone-wait crossover from analytics lies in the paper's Table 3 range. |
| E2 | `sim/stats.py::estimate_crossover_ci` | Bootstrap covers seed noise but not bias from linear interpolation on a coarse ρ grid. This is the likely cause of R1's 95% CIs excluding the analytic ρ\* at (4,6) and (10,9). | Measure the bias by running the estimator on **exact analytic** values at the same grid. Then either refine the grid near the crossover (step ≤ 0.005) or fit a smooth curve (e.g., cubic spline) inside each bootstrap replicate. Report bias alongside the CI. | On analytic inputs, the estimator's error must be < 0.001 after the fix. R1's CI must then contain the analytic ρ\* (or the remaining gap must be reported and explained). |
| E3 | `sim/scheduler.py`, `jsq` routing | Routes by fewest drones **waiting**. An idle pad and a busy pad with an empty queue both count 0, so drones can be sent to a busy pad while another is idle. | Route by fewest drones **in system** (waiting + charging). Break ties uniformly at random using a **separate RNG stream** so tie-breaking does not disturb the arrival/service streams (keeps common random numbers valid). | With 2 pads, one busy and one idle, zero waiting: an arrival must go to the idle pad 100% of the time. |
| E4 | `jsq_travel` | (a) Cost written as `travel_time/speed` (time divided by speed). (b) Uses waiting count, not in-system. (c) Unclear whether travel actually delays arrival at the pad. (d) Compared against a concentrated baseline with no travel, which changes two things at once. | Cost J = in_system[j]/μ + distance(origin, j)/speed. Arrival at the pad must be scheduled as an event at t + τ_ij. Build a **concentrated-with-travel** baseline (hub at the centroid of the distributed station positions) and compare R3b against it. Run R3b on **≥ 5 random station layouts**. | Unit test: dimensionally, cost is in minutes. Event test: a drone routed at t reaches the pad queue at exactly t + τ_ij. |
| E5 | Phase 4 `order='priority'` pad queue | Pad queue served by **lowest margin first**. Queued drones have landed (assumption A6), so their SoC cannot fall and there is no safety reason to prioritise them. Lowest SoC also means longest charge, so this is effectively longest-job-first, which maximises average waiting. Kleinrock's conservation law no longer applies once CC–CV makes charge times unequal, so ordering matters here. | Remove margin-based pad-queue ordering. Under our method (Section 3), service order at a pad is **reservation order**, and reservations are created in priority order (F9). Keep the old behaviour only as a labelled ablation (`pad_order='margin'`). | With two queued drones at SoC 0.2 and 0.6 and equal mission urgency, `pad_order='margin'` must serve 0.2 first (confirms ablation), and our method must follow reservation order. |
| E6 | Reachability gate `_reachable_with_return` | Must hold the reserve σ **on arrival at the station**, not at the mission destination, and must include the leg from the drone's current position to the mission origin. | Use F5 exactly (Section 2). | Construct a drone that can reach the destination with ≥ σ but would reach the nearest station with < σ: dispatch must be refused. |
| E7 | Phase 4 mission ordering | Orders missions by d_k − t. That is time-to-deadline, not slack. | Use mission slack F10. | A mission with a later deadline but a much longer flight must be ranked more urgent when its slack is smaller. |
| E8 | `sim/milp.py` C9 (CC–CV) | A slot uses the rate of the band it **starts** in for the whole slot. With Δt = 10 min and B = 90 Wh, one 200 W slot adds ~37% SoC, more than any band is wide, so a drone starting at 69% is charged at the fast rate past 100%. The CC–CV MILP does not actually enforce CC–CV. | Keep the band indicators z[i,t,l]. Replace the single increment with the **exact within-slot curve** for each starting band (F13). | For each starting SoC on a fine grid, the MILP's maximum next-slot SoC must equal `soc_after_charging(S, Δt)` within 1e-6. |
| E9 | `sim/milp.py` C10 | Dwell window must be truncated at the horizon end, or it can forbid starting a charge in the final slots. | Truncate the window at T. | A drone that needs exactly one slot in the final slot must be feasible. |
| E10 | Phase 5 interpretation | The 0% gap is explained as least-slack-first being "near-provably optimal." Actual reason: the v1 objective (total pad-slots) is **constant** across schedules that do not overcharge. The result only shows the heuristic finds a feasible schedule when one exists. | Correct the explanation in `CLAUDE.md` and the report. Replace the objective with F12 (Section 4). | No test; documentation change. |
| E11 | Write-up | κ = 0.5 Wh/m is attributed to "the paper's own example." It came from the project's own draft notes; Wang et al. have no energy model. | Fix the wording. | — |
| E12 | Write-up | H5 is described as "contradicted." H5 predicted makespan and deadline-miss results; only energy was measured. | Mark H5 as **untested** until experiment X5 runs. | — |
| E13 | Phase 6 energy results | Total charged energy tracks work done and number of trips, not efficiency. The fleet-size sweep also changes drones per station (2.5, 5, 4, 4, 4) and the layout at every size. | Re-analyse under X5 with energy decomposition, per-mission normalisation, and multiple layouts. Until then, label the sign-reversal result **provisional**. | — |

**Do not delete old results.** Mark affected results as *superseded* in `CLAUDE.md` Section 8, with a pointer to the new run that replaces them.

---

## 2. Our proposed formulas — authoritative specification

These are the formulas the new code must implement. Each has an ID; reference the ID in code comments and tests.

### F1. Flight power model (configurable)

$$P(v,m) = \beta_0 + \beta_1 m + \beta_2 v^2 + \frac{\beta_3}{v} \qquad \text{[W]}$$

v = airspeed (m/s), m = payload mass (kg). Coefficients β0–β3 must come from the user (hardware calibration). **Do not invent values.**

### F2. Leg energy

$$E_{pq} = P(v,m)\cdot\frac{\lVert p-q\rVert}{v}\cdot\frac{1}{3600} + E_{to} + E_{land} \qquad \text{[Wh]}$$

Implement a config switch `ENERGY_MODEL = "flat" | "power"`:
- `"flat"`: E_pq = κ·‖p − q‖ + E_to + E_land, with κ = 0.01 Wh/m (current validated value).
- `"power"`: F1 + F2. Only usable once the user supplies β0–β3.

E_to and E_land are parameters (Wh). Ask the user for values (Section 7). If none are given, set both to 0 and log that this is an assumption. Results must state which model was used.

### F3. SoC recurrence

$$S_i(t+\Delta t) = S_i(t) - \frac{e_i(t)}{B} + \frac{\eta\, r(S_i(t))\,\Delta t}{60\,B}\,x_i(t)$$

where r(S) is the CC–CV band rate at the current SoC (F4), and a drone never flies and charges in the same step. Use the existing `soc_after_charging`, which already handles band crossings within a step.

### F4. CC–CV charging curve and charge time

Bands (default until measured data exists): 0–0.70 → 200 W; 0.70–0.90 → 120 W; 0.90–1.00 → 50 W.

$$T^{chg}(S^{arr}, S^{tgt}) = \sum_{\ell}\frac{60\,B\,\big|[S^{arr},S^{tgt}]\cap[\mathrm{lo}_\ell,\mathrm{hi}_\ell]\big|}{\eta\, r_\ell} \qquad \text{[min]}$$

That is, the time spent in each band is the SoC gained in that band times B, divided by the effective power. Use the existing `time_to_reach_target_min`; add a test that it equals this formula.

### F5. Reachability gate (feasibility, evaluated before any decision)

**Modelling decision (2026-09-22, recorded in `CLAUDE.md` Section 13):** missions have a single work site (`destination`), not a separate pickup point (`origin`) distinct from the drone's current position. This matches the code as built (`sim/models.py`'s `Mission` has no `origin` field) and is now the spec, not a gap. Stated as a simplification in the paper: a mission is "go to `destination` and perform the task there," not "go to `origin`, pick up, deliver to `destination`." If a future version needs a genuine pickup leg, `origin` would need to be added to `Mission` and F5/F6/F10 extended back to three legs.

**Station gate** (can drone i reach station j safely?):
$$F_i(t) = \Big\{\, j \;:\; S_i(t) - \frac{e_{ij}}{B} \ge \sigma \,\Big\}$$

**Dispatch gate** (can drone i fly mission k from where it is?):
$$S_i(t) - \frac{e_{i \to d_k} + \min_{j} e_{d_k \to j}}{B} \;\ge\; \sigma$$

where d_k is the mission destination. The reserve σ must hold **on arrival at the station**. The gate is a hard filter: stations or missions that fail it are never scored. Never fold it into a weighted cost.

### F6. Arrival SoC and target SoC

$$S_i^{arr} = S_i(t) - \frac{e_{ij}}{B}$$

$$S_i^{req} = \frac{e_{j \to d_k} + \min_{j'} e_{d_k \to j'}}{B}$$

for the drone's next expected mission k (the most demanding mission releasing within the lookahead window, as in the existing adaptive policy).

$$S_i^{tgt} = \min\!\Big(1,\; \max\big(S_i^{req} + \sigma,\; S_{trigger} + 0.05\big)\Big)$$

The floor S_trigger + 0.05 prevents the zero-duration charge loop found earlier. If no mission is expected, S_tgt = 1.

### F7. Deterministic waiting time from reservation lists

Each station j has c_j pads. Each pad p keeps `free_time[p]`: the time at which the last drone reserved on it will finish charging (equal to the current time if the pad is idle and unreserved).

For a drone arriving at station j at time t_arr:
$$\text{start}_j(t_{arr}) = \max\!\Big(t_{arr},\ \min_{p\in \text{pads}(j)} \text{free\_time}[p]\Big)$$
$$W_j(t_{arr}) = \text{start}_j(t_{arr}) - t_{arr}$$

**This waiting time is exact, not an estimate**, whenever travel times and charge durations are deterministic, which they are in the Phase 4 simulator (CC–CV with known arrival SoC). Use F7 in the mission simulator. In the Phase 3 queue-only model, service times are random, so there the expected value in_system/μ is the correct analogue (E4).

### F8. Time-to-ready cost and station choice

$$J_{ij}(t) = \tau_{ij} + W_j(t + \tau_{ij}) + T^{chg}\big(S_i^{arr}, S_i^{tgt}\big)$$
$$j^* = \arg\min_{j \in F_i(t)} J_{ij}(t)$$

All three terms are in minutes, so no weights are needed. The queue term is evaluated at the **arrival time** t + τ_ij, not now.

### F9. Reservation update (mandatory)

After choosing j\* for drone i:
```
p* = argmin over pads p of station j* of free_time[p]
start = max(t + tau_ij*, free_time[p*])
end   = start + T_chg(S_arr, S_tgt)
free_time[p*] = end
append (i, p*, start, end) to reservation list Q_j*
```
The update happens **before** the next drone in the same epoch is evaluated. Service at each pad follows reservation order. Without this step every drone picks the same station.

### F10. Slack

**Charging slack for drone i** (urgency):
$$\text{slack}_i = d_i - \big(t + \text{flight\_time}_i\big)$$
where d_i is the deadline of drone i's next assigned mission, and flight_time_i is the time to fly from the drone's current position directly to that mission's destination (2-leg model, F5's note). If drone i has no assigned mission, slack_i = SLACK_CAP (a large constant, e.g., the horizon length).

**Mission slack** (for assigning missions, replaces d_k − t):
$$\text{slack}_k = d_k - \big(t + \tau_{i \to d_k}\big)$$
using the nearest idle drone that passes the dispatch gate. Matches `sim/mission_sim.py::_mission_slack` (REMEDIATION.md E7 fix).

### F11. Margin and combined priority

$$\text{margin}_i = S_i(t) - \sigma - \frac{\min_j e_{ij}}{B}$$

The original priority is w₁/slack + w₂/margin, but slack is in minutes and margin is a fraction, so the weights would carry units. Implement a normalised form:

$$\text{prio}_i = w_1\,\frac{T_{ref}}{\max(\text{slack}_i,\ \varepsilon_t)} + w_2\,\frac{\sigma}{\max(\text{margin}_i,\ \varepsilon_s)}$$

- T_ref = full 0→100% charge time from F4 (≈ 39 min at defaults).
- ε_t = 1 min, ε_s = 0.01.
- If slack_i ≤ 0 or margin_i ≤ 0, set prio_i = +∞ (handle first).
- margin_i < 0 means the drone cannot reach any station with its reserve intact: log a SAFETY_VIOLATION. With a correct dispatch gate this count should be 0.
- Default w₁ = w₂ = 1; confirm with the user (Section 7), then run a weight sweep as an experiment rather than hand-picking.

Margin is used **only** to rank drones that are deciding whether and where to charge (they may be flying). It is **never** used to reorder drones already queued at a pad (see E5).

### F12. Objective (for the MILP and for reporting heuristic runs)

$$\min Z = \alpha\, C_{max} + \beta \sum_{i,j,t} \pi_{jt}\, r_j\, \frac{\Delta t}{60}\, x_{ijt} + \gamma \sum_k T_k$$

C_max = completion time of the last mission; T_k = max(0, C_k − d_k); π_jt = tariff at station j in slot t. Report Z and its three terms separately for **every** policy, so heuristic and MILP are judged on the same scale. Weights α, β, γ: ask the user (Section 7).

### F13. Exact within-slot CC–CV constraint for the MILP (fixes E8)

For a drone starting a slot at SoC S in band l, the SoC after charging for Δt, Φ_l(S), is continuous, increasing and **concave within band l**: slope 1 while the endpoint stays in band l, then slope r_{l+1}/r_l once the endpoint crosses into band l+1, then r_{l+2}/r_l, and so on (slopes strictly decreasing). So Φ_l can be written exactly as the minimum of its linear pieces:

$$\Phi_l(S) = \min_k \big(a_{l,k}\, S + b_{l,k}\big), \quad \Phi_l(S) \le 1$$

MILP constraints for every drone i, slot t, band l, piece k:

$$S_{i,t+1} \le a_{l,k}\, S_{i,t} + b_{l,k} + M\big(2 - x^{tot}_{i,t} - z_{i,t,l}\big)$$

Compute the pieces (a_{l,k}, b_{l,k}) numerically from `soc_after_charging` at the breakpoints, and verify them in a test (E8). Note: Φ is **not** concave across a change of *starting* band (slope jumps up when the start crosses into a slower band), so the band indicators z are genuinely needed. Keep the existing `S_{i,t+1} ≤ S_{i,t} + M·x^{tot}_{i,t}` and `S_{i,t+1} ≥ S_{i,t}` constraints.

### F14. Just-in-time dispatch (arrival-time control)

This is how our method controls **when** a drone arrives, which is the research question in `CLAUDE.md` Section 2. With a reservation (start time known from F9), drone i departs for station j\* at

$$t^{dep}_i = \max\big(t,\ \text{start} - \tau_{ij^*}\big)$$

so it arrives when its pad frees instead of queueing on the pad. Waiting happens where the drone already is (landed, no energy use).

**Accounting rule (mandatory):** a drone's charging delay is always measured as *charge start − charge request time*, regardless of where it waited. Moving waiting off the pad must never make it disappear from the metrics. Report on-pad queue length and total delay separately.

---

## 3. The full heuristic (our method)

**Energy-Aware Least-Slack-First with Pad Reservation.** Implement as a policy `policy='ours'` in the Phase 4 mission simulator, with a flag for each component so ablations can switch them off one at a time.

```
at each decision epoch t (every step, rolling horizon):

  # 1. which drones need a charging decision
  C = drones not already holding a reservation, and
      (S_i(t) <= S_trigger  OR  next mission fails the dispatch gate F5)

  # 2. rank them
  for i in C: compute slack_i (F10), margin_i and prio_i (F11)
  sort C by prio_i descending

  # 3. assign stations with reservation
  for i in C:
      F_i = station gate (F5)
      if F_i empty: log SAFETY_VIOLATION; continue
      S_tgt = F6
      for j in F_i: J_ij = tau_ij + W_j(t + tau_ij) + T_chg(S_arr_ij, S_tgt)   # F7, F8
      j* = argmin J_ij
      reserve pad at j*  (F9)            # updates free_time before next drone
      schedule departure at t_dep (F14)  # or t, if JIT is disabled

  # 4. assign missions to idle, charged drones by least mission slack (F10),
  #    subject to the dispatch gate (F5)

  # 5. advance one step: flight energy, charging (F3), events, bookkeeping
```

**Ablation flags** (each removes exactly one component):

| Flag | Effect when off |
|---|---|
| `use_queue_term` | Drops W_j from F8 → becomes nearest-time greedy (= baseline B3) |
| `use_reservation` | No F9 update within an epoch (stampede allowed) |
| `use_priority` | Process drones in request order instead of F11 |
| `use_partial` | S_tgt = 1 always |
| `use_jit` | Depart immediately instead of F14 |
| `use_charge_time_term` | Drops T_chg from F8 |

---

## 4. MILP v2 — the real objective (replaces the constant-objective v1)

Small instances only (e.g., N ≤ 8 drones, K ≤ 10 missions, 2–3 stations, T ≤ 36 slots of 10 min). Simplification, to be stated in the paper: stations are at a depot, missions start and end at the depot, and each mission k has a known duration D_k (slots) and energy e_k (Wh) that already include travel.

Variables:
- x_{ijt} ∈ {0,1}: drone i charges at station j in slot t
- u_{ikt} ∈ {0,1}: drone i starts mission k in slot t (only for t ≥ release ρ_k)
- S_{it} ∈ [σ, 1]; z_{itl} ∈ {0,1} band indicators (F13)
- C_k, T_k ≥ 0; C_max ≥ 0

Constraints:
- C1 pad capacity: Σ_i x_{ijt} ≤ c_j
- C2 one station: Σ_j x_{ijt} ≤ 1
- C5 every mission done once: Σ_{i,t} u_{ikt} = 1 (y_ik = Σ_t u_{ikt})
- Flying status: f_{it} = Σ_k Σ_{t'=t−D_k+1}^{t} u_{ikt'}; exclusivity (A5): f_{it} + Σ_j x_{ijt} ≤ 1
- Energy: S_{i,t+1} ≤ S_{it} + (charging per F13) − Σ_k (e_k/B)·u_{ikt}, and S ≥ σ throughout (so no mission starts without enough charge)
- C6 completion and tardiness: C_k = Σ_{i,t} (t + D_k)·Δt·u_{ikt}; T_k ≥ C_k − d_k; T_k ≥ 0
- C7: C_max ≥ C_k
- C9 = F13, C10 as fixed in E9

Objective: F12.

Heuristic comparison: run `policy='ours'` on the **same** instance, using a discretised version of the Phase 4 simulator with identical simplifications. Report the gap on Z and on each of its three terms. A nonzero gap is now possible and expected; report whatever comes out.

Hand-checkable instance (required): 2 drones, 1 station with 1 pad, 2 missions. Work out the optimal Z by hand in the test docstring and assert the MILP reproduces it.

---

## 5. Tests to write before any experiment

`tests/test_formulas.py`
- F4: `time_to_reach_target_min` equals the band-sum formula for several (S_arr, S_tgt) pairs, including crossings of both boundaries.
- F5: the E6 counter-example is refused; a clearly feasible mission is accepted.
- F6: S_tgt never falls below S_trigger + 0.05; S_tgt ≤ 1.
- F7: with pads free at [10, 25] and t_arr = 5, W = 5; with t_arr = 30, W = 0.
- F8: a station 2 km away with an empty queue beats one 500 m away with three reservations, when that is what the times imply (construct the numbers).
- F9 (**stampede test**): 6 drones requesting at the same epoch, 3 stations × 1 pad, equal distances. With reservation on, reservations spread across all 3 stations; with reservation off, the ablation sends them all to one.
- F10/F11: priority ordering on hand-built cases; slack ≤ 0 or margin ≤ 0 → handled first; no division errors.
- F14: under JIT, total delay (start − request) is identical to the non-JIT delay in a deterministic single-station scenario, while on-pad queue length drops to 0.

`tests/test_prediction.py`
- **Deterministic waiting-time check:** in the Phase 4 simulator with no randomness after dispatch, the W_j predicted at reservation time must equal the realised wait for **every** drone (tolerance: one time step). Any mismatch is a bug. This directly tests the project's claim that W_j is exact in a scheduled system.

`tests/test_fixes.py`
- One test per fix E1–E9 (see Section 1).

`tests/test_regression.py`
- Existing Phase 1/2 validation and both Phase 3 sanity checks (slack-zero reduction, Kleinrock conservation) still pass after all changes.

---

## 6. Experiments to run (after tests pass)

Run each first at a tiny scale to check it works and estimate runtime; report the estimate before the full run. Every run: raw per-run CSV in `results/` (new timestamped files), CRN across policies, ≥ 30 seeds for final numbers, 95% CIs, paired Wilcoxon tests.

**X1. Corrected crossover (queue-only model).** Regimes R1, R2, R3a (fixed JSQ), R3b (fixed, vs concentrated-with-travel, ≥ 5 layouts), plus **R4 = R3a + JIT dispatch (F14)**. Primary metric: per-drone waiting-time crossover ρ\*_t. Also report total-queue crossover and blocking. Points: (4,6), (5,7), (10,9). Use the bias-corrected estimator (E2).
Note for R4: in a queue-only model with total delay counted correctly, JIT is expected to move waiting off the pad without reducing total delay. Report what actually happens.

**X2. Estimator bias.** The E2 check on analytic inputs, reported as a table.

**X3. Our method vs baselines (the paper's main comparison).** Phase 4 mission simulator, same seeds and layouts for all policies:
- B1 Threshold: charge to 100% when S ≤ S_trigger, nearest station
- B2 FCFS: first requester gets first free pad, nearest station
- B3 Nearest-time greedy: our method with `use_queue_term=False` (**the key ablation for the queue-aware claim**)
- B4 JSQ: fewest drones in system, no reservation
- **Ours**: all components on
- Ablations: each flag in Section 3 turned off one at a time

Metrics: F12 total and its three terms, deadline miss rate, makespan, mean and 95th-percentile charging delay, on-pad queue length, station utilisation, energy per completed mission, safety violations, gate binding rate, runtime per decision. Sweep mission load (light / nominal / saturated) and station density (scarce / balanced / abundant).

**X4. Layout crossover in the mission model (the research question end-to-end).** Same total number of pads in two layouts: one hub with n pads vs n stations with 1 pad each (spread over the area). Sweep load. For each policy in X3, find the load at which the better layout switches, using per-drone charging delay and miss rate. This answers whether the reference paper's crossover survives once charging is scheduled.

**X5. Energy and H5, done properly.** Repeat the Phase 6 fleet / density / load sweeps for full vs partial charging (`use_partial` on/off within `ours`, and the old adaptive policy for continuity):
- Keep drones per station fixed across fleet sizes, or vary it as a separate sweep; never both at once.
- ≥ 5 random layouts per configuration.
- Decompose energy: mission flight + trips to/from stations + change in stored charge at the end of the run.
- Normalise per completed mission.
- **Test H5 directly:** makespan and deadline miss rate, full vs partial.

**X6. Prediction accuracy.** Distribution of (predicted W_j − realised wait) across all reservations in X3 runs. Expected to be zero in the deterministic simulator; any spread must be explained.

**X7. MILP v2 gap.** Section 4, ≥ 20 feasible instances. Report gap on Z and per term, and solver time.

**X8. Weight sensitivity.** Sweep w₁/w₂ (F11) and α, β, γ (F12) on a small grid; report how results change. Do not select weights to favour any hypothesis.

---

## 7. Open decisions — ask the user before coding

1. **Flight energy:** stay with `flat` (κ = 0.01 Wh/m) or provide β0–β3 for `power`? Values for E_to and E_land (Wh), or 0?
2. **Priority weights:** accept normalised F11 with w₁ = w₂ = 1 as the default, then sweep in X8?
3. **Objective weights** α, β, γ for F12, and the tariff profile π_jt (flat or time-of-use, with times).
4. **JIT dispatch (F14):** on by default in `ours`, or treat it as an ablation only?
5. **Layouts:** area size, number of random layouts per configuration (default 5), hub position for concentrated layouts (default centroid).
6. **Lookahead window** for S_req (current 30 min) and S_trigger (current 0.35): keep?

Record each answer in `CLAUDE.md` Section 13 with the date.

---

## 8. Updates to `CLAUDE.md` and the results report

After the fixes and experiments, update:
- Section 8 phase statuses: mark superseded results and link the replacement runs.
- Section 9 hypotheses: H5 → untested until X5; H3 re-evaluated on ρ\*_t (X1); H6 re-evaluated on X7.
- Remove from "strongest results": the 0% MILP gap (E10) and the energy sign reversal, until X5 confirms or overturns it.
- Add the E1 finding (per-pad vs whole-hub comparison in the reference paper) as a methodological result.
- Record every open-decision answer.

In the results report, revise: the Phase 3 headline (now X1), the Phase 5 explanation (E10), H5 wording (E12), κ attribution (E11), and label the Phase 6 energy findings provisional (E13).

---

## 9. Order of work and checkpoints

1. Ask the Section 7 questions; propose a plan; wait for approval.
2. Fix E3, E4, E5, E6, E7 (quick checks that may change results). Tests first. **Checkpoint: report.**
3. Fix E1, E2; run X1 and X2. **Checkpoint: report ρ\*_t results.**
4. Implement F1–F14 and the full heuristic (Section 3) with ablation flags; pass all Section 5 tests, especially the stampede and deterministic-prediction tests. **Checkpoint: report.**
5. Run X3, X4, X6. **Checkpoint: report** — this is the paper's main result.
6. Run X5.
7. Fix E8, E9; build MILP v2; run X7.
8. Run X8.
9. Update `CLAUDE.md` and the report (Section 8).

At every checkpoint, report the commands run, real output, anything that failed or looks suspicious, and results that contradict a hypothesis. Do not proceed past a checkpoint until the user has seen the report.
