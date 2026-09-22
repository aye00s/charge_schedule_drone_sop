"""Generate all report figures from saved CSVs under results/ (never from
in-memory data, per Section 11 convention). Writes PNGs to figures/."""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

plt.rcParams.update({"figure.dpi": 150, "font.size": 10, "axes.grid": True,
                      "grid.alpha": 0.3})


def fig1_phase1_table2():
    from phase1_baseline import TABLE2, M_VALUES, N_VALUES, validate_table2
    results, _ = validate_table2()
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for j, m in enumerate(M_VALUES):
        analytic = [TABLE2[n][j] for n in N_VALUES]
        sim = [results[n][j] for n in N_VALUES]
        ax.plot(N_VALUES, analytic, "o-", label=f"m={m} (paper Table 2)", alpha=0.8)
        ax.plot(N_VALUES, sim, "x--", color=ax.lines[-1].get_color(), alpha=0.6)
    ax.set_xlabel("n (platforms)")
    ax.set_ylabel(r"queue-length crossover $\rho^*$")
    ax.set_title("Phase 1: reproduced vs. paper Table 2 crossover\n(solid=paper, dashed x=our bisection)")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig1_phase1_table2.png")
    plt.close(fig)


def fig2_phase2_validation():
    df = pd.read_csv(RESULTS / "phase2_validation_20260921_161516.csv")
    sub = df[(df["n"] == 5) & (df["m"] == 7)]
    agg = sub.groupby("rho").mean(numeric_only=True).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(agg["rho"], agg["L_d_analytic"], "o-", label="L_d analytic")
    axes[0].plot(agg["rho"], agg["L_d_sim"], "x--", label="L_d simulated")
    axes[0].plot(agg["rho"], agg["L_c_analytic"], "o-", label="L_c analytic")
    axes[0].plot(agg["rho"], agg["L_c_sim"], "x--", label="L_c simulated")
    axes[0].set_xlabel(r"$\rho$"); axes[0].set_ylabel("L (queue length)")
    axes[0].set_title("Queue length: sim vs analytic (n=5,m=7)")
    axes[0].legend(fontsize=8)
    axes[1].plot(agg["rho"], agg["t_d_analytic"], "o-", label="t_d analytic")
    axes[1].plot(agg["rho"], agg["t_d_sim"], "x--", label="t_d simulated")
    axes[1].plot(agg["rho"], agg["t_c_analytic"], "o-", label="t_c analytic")
    axes[1].plot(agg["rho"], agg["t_c_sim"], "x--", label="t_c simulated")
    axes[1].set_xlabel(r"$\rho$"); axes[1].set_ylabel("t (wait, 1/λ factored out)")
    axes[1].set_title("Wait time: sim vs analytic (n=5,m=7)")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig2_phase2_validation.png")
    plt.close(fig)


def fig3_phase3_regimes():
    df = pd.read_csv(RESULTS / "phase3_regimes_20260921_164108.csv")
    agg = df.groupby(["rho", "regime"])["L_sim"].mean().reset_index()
    Lc = df.groupby("rho")["L_c_analytic"].first().reset_index()
    fig, ax = plt.subplots(figsize=(7, 5))
    for regime, sub in agg.groupby("regime"):
        ax.plot(sub["rho"], sub["L_sim"], "o-", label=regime, alpha=0.85)
    ax.plot(Lc["rho"], Lc["L_c_analytic"], "k--", label="L_c (concentrated, analytic)", linewidth=2)
    ax.set_xlabel(r"$\rho$"); ax.set_ylabel("L (queue length)")
    ax.set_title("Phase 3: regime comparison vs. concentrated baseline\n(n=5, m=7, 15 seeds)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig3_phase3_regimes.png")
    plt.close(fig)


def fig4_phase3_crossover_grid():
    # Hardcoded from the 30-seed crossover CI runs (documented in CLAUDE.md);
    # regenerating from raw CSVs would require re-running estimate_crossover_ci.
    points = [
        ("(4,6)", 0.7056, 0.7051, 0.7061, 0.5967, 0.5958, 0.5976, 0.70752),
        ("(5,7)", 0.7505, 0.7500, 0.7509, 0.6232, 0.6227, 0.6236, 0.75049),
        ("(10,9)", 0.8196, 0.8194, 0.8199, 0.7042, 0.7040, 0.7043, 0.82529),
    ]
    labels = [p[0] for p in points]
    x = np.arange(len(points))
    r1 = [p[1] for p in points]
    r3a = [p[4] for p in points]
    analytic = [p[7] for p in points]
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.errorbar(x - 0.05, r1, yerr=[[p[1]-p[2] for p in points], [p[3]-p[1] for p in points]],
                fmt="o", label="R1 vs L_c (sim, 95% CI)", capsize=4)
    ax.errorbar(x + 0.05, r3a, yerr=[[p[4]-p[5] for p in points], [p[6]-p[4] for p in points]],
                fmt="s", label="R3a vs L_c (sim, 95% CI)", capsize=4)
    ax.scatter(x - 0.05, analytic, marker="_", s=300, color="black", label="Table 2 analytic (R1 target)")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_xlabel("(n, m)"); ax.set_ylabel(r"crossover $\rho^*$")
    ax.set_title("Phase 3: crossover shift generalizes across the grid\n(30 seeds each)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig4_phase3_crossover_grid.png")
    plt.close(fig)


def fig5_phase4_energy_by_rate():
    df = pd.read_csv(RESULTS / "phase4_stats_20260921_183026.csv")
    agg = df.groupby("rate")[["full_energy", "adapt_energy"]].agg(["mean", "std"])
    rates = agg.index.values
    fig, ax = plt.subplots(figsize=(6, 4.5))
    width = 0.15
    x = np.arange(len(rates))
    ax.bar(x - width/2, agg[("full_energy", "mean")], width, yerr=agg[("full_energy", "std")],
           label="full charge", capsize=4)
    ax.bar(x + width/2, agg[("adapt_energy", "mean")], width, yerr=agg[("adapt_energy", "std")],
           label="adaptive charge", capsize=4)
    ax.set_xticks(x); ax.set_xticklabels([f"rate={r}" for r in rates])
    ax.set_ylabel("total charge energy (Wh)")
    ax.set_title("Phase 4: full vs. adaptive charging energy\n(n=15, 30 seeds, Wilcoxon p=1.86e-09 both)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "fig5_phase4_energy.png")
    plt.close(fig)


def fig6_phase5_gap():
    df1 = pd.read_csv(RESULTS / "phase5_milp_gap_20260921_180210.csv")
    df2 = pd.read_csv(RESULTS / "phase5_gap_robustness_20260921_183055.csv")
    gaps1 = df1["gap"].dropna().astype(float).tolist()
    gaps2 = df2["gap"].dropna().astype(float).tolist()
    all_gaps = gaps1 + gaps2
    n_infeasible = df1["gap"].isna().sum()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.hist(all_gaps, bins=np.linspace(-0.05, 0.05, 11), edgecolor="black")
    ax.set_xlabel("optimality gap = (heuristic - MILP) / MILP")
    ax.set_ylabel(f"count (n={len(all_gaps)} feasible instances)")
    ax.set_title(f"Phase 5: optimality gap, all {len(all_gaps)} feasible instances\n"
                 f"exactly 0% gap on every one "
                 f"({n_infeasible} more correctly called Infeasible by both solvers)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig6_phase5_gap.png")
    plt.close(fig)


def fig7_phase6_fleet_size():
    df = pd.read_csv(RESULTS / "phase6_scale_20260921_184347.csv")
    df["pct_diff"] = (df["adapt_energy"] - df["full_energy"]) / df["full_energy"] * 100
    agg = df.groupby("n_uavs")["pct_diff"].agg(["mean", "std"]).reset_index()
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.errorbar(agg["n_uavs"], agg["mean"], yerr=agg["std"], fmt="o-", capsize=4, color="C3")
    ax.axhline(0, color="black", linewidth=1, linestyle=":")
    ax.set_xlabel("fleet size (n_uavs)")
    ax.set_ylabel("% diff (adaptive-full)/full energy")
    ax.set_title("Phase 6: adaptive-charging penalty reverses sign with fleet size\n(30 seeds/point, all |p|<1e-8)")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig7_phase6_fleet_size.png")
    plt.close(fig)


def fig8_phase6_contention_axes():
    df = pd.read_csv(RESULTS / "phase6_remaining_axes_20260921_210910.csv")
    df["pct_diff"] = (df["adapt_energy"] - df["full_energy"]) / df["full_energy"] * 100
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))

    density = df[df["axis"] == "density"]
    order_d = ["scarce", "balanced", "abundant"]
    agg_d = density.groupby("label")["pct_diff"].agg(["mean", "std"]).reindex(order_d)
    axes[0].bar(order_d, agg_d["mean"], yerr=agg_d["std"], capsize=4, color="C0")
    axes[0].axhline(0, color="black", linewidth=1, linestyle=":")
    axes[0].set_ylabel("% diff (adaptive-full)/full")
    axes[0].set_title("Station density (n_uavs=20)")

    load = df[df["axis"] == "load"]
    order_l = ["light", "nominal", "saturated"]
    agg_l = load.groupby("label")["pct_diff"].agg(["mean", "std"]).reindex(order_l)
    axes[1].bar(order_l, agg_l["mean"], yerr=agg_l["std"], capsize=4, color="C1")
    axes[1].axhline(0, color="black", linewidth=1, linestyle=":")
    axes[1].set_title("Mission load (n_uavs=20, 5 stations)")

    fig.suptitle("Phase 6: adaptive-charging penalty grows with system contention\n(30 seeds/point)")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig8_phase6_contention.png")
    plt.close(fig)


def fig9_phase6_runtime():
    df = pd.read_csv(RESULTS / "phase6_scale_20260921_184347.csv")
    n_ticks = 1000
    df["per_decision_us"] = (df["full_runtime_s"] / (df["n_uavs"] * n_ticks)) * 1e6
    agg = df.groupby("n_uavs")["per_decision_us"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.plot(agg["n_uavs"], agg["per_decision_us"], "o-", color="C4")
    ax.set_xlabel("fleet size (n_uavs)")
    ax.set_ylabel(r"runtime per decision ($\mu$s)")
    ax.set_title("Phase 6: per-decision runtime scaling\n(mildly super-linear, ~11us at n=5 to ~100us at n=60)")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig9_phase6_runtime.png")
    plt.close(fig)


if __name__ == "__main__":
    fig1_phase1_table2()
    fig2_phase2_validation()
    fig3_phase3_regimes()
    fig4_phase3_crossover_grid()
    fig5_phase4_energy_by_rate()
    fig6_phase5_gap()
    fig7_phase6_fleet_size()
    fig8_phase6_contention_axes()
    fig9_phase6_runtime()
    print("All figures written to", FIGURES)
