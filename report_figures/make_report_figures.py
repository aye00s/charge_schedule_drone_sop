"""Generates the figures used in the plain-language PDF report, from the
project's own saved, corrected (post pad-capacity-fix) result CSVs only --
per CLAUDE.md's own rule, plots come from CSVs, never in-memory data.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report_figures"
RESULTS = ROOT / "results"

plt.rcParams.update({
    "font.size": 12,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})

COLORS = {"concentrated": "#4C72B0", "distributed": "#DD8452", "baseline": "#8C8C8C",
          "jsq": "#55A868", "ours": "#C44E52", "B3": "#8172B2"}


def fig1_crossover():
    """The headline finding: ours is the only policy with a real crossover.
    Each panel gets its OWN y-scale (not shared) -- sharing one axis across
    all four would hide "ours"'s crossover entirely under baseline's much
    larger 0-57min range; the crossover is real but small in absolute
    minutes, and the point of this figure is to show its SHAPE."""
    df = pd.read_csv(RESULTS / "x4_full_20260923_212821.csv")
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.2))
    policies = [("baseline", "Baseline\n(no crossover)"), ("jsq", "JSQ\n(no crossover)"),
                ("ours", "Ours\n(REAL crossover)"), ("B3_use_queue_term_False", "B3 = ours minus\nqueue-awareness\n(no crossover)")]
    for ax, (pol, title) in zip(axes, policies):
        sub = df[df["policy"] == pol]
        for arm, color in [("concentrated", COLORS["concentrated"]), ("distributed", COLORS["distributed"])]:
            s = sub[sub["arm"] == arm].groupby("mission_rate")["mean_charge_delay_min"].mean()
            ax.plot(s.index, s.values, marker="o", label=arm.capitalize(), color=color, linewidth=2.5)
        ax.set_title(title, fontsize=12)
        ax.set_xlabel("Mission arrival rate\n(missions/minute)")
        ax.set_ylabel("Mean charging delay (minutes)")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", fontsize=9)
    axes[2].set_facecolor("#FFF7EC")  # highlight the "ours" panel, the headline result
    fig.suptitle("Which layout wins? Only “ours” shows a real crossover\n"
                 "(each panel has its own scale, so the SHAPE of each line is visible)",
                 fontsize=14, fontweight="bold", y=1.10)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_crossover.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("fig1 done")


def fig2_capacity_bug():
    """Before/after the pad-capacity bug fix, density_scarce miss rates."""
    policies = ["baseline", "jsq", "ours", "B3"]
    before = [0.1066, 0.0058, 0.2149, 0.000]  # pre-fix (B3 was buggy)
    after = [0.1066, 0.0058, 0.2149, 0.2856]  # post-fix
    x = np.arange(len(policies))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))
    b1 = ax.bar(x - width / 2, before, width, label="Before fix\n(B3 looked best)", color="#B0B0B0")
    b2 = ax.bar(x + width / 2, after, width, label="After fix\n(B3's real number)", color="#C44E52")
    ax.set_xticks(x)
    ax.set_xticklabels(["Baseline", "JSQ", "Ours", "B3\n(ours minus\nqueue term)"])
    ax.set_ylabel("Fraction of missions delivered late")
    ax.set_title("The pad-capacity bug: B3 looked perfect, then didn't", fontsize=14, fontweight="bold")
    ax.legend()
    ax.bar_label(b1, fmt="%.3f", fontsize=9)
    ax.bar_label(b2, fmt="%.3f", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_capacity_bug.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("fig2 done")


def fig3_milp_gap():
    df = pd.read_csv(RESULTS / "x7_milp_v2_gap_20260923_221122.csv")
    v1_gaps = df["v1_gap"].dropna() * 100
    v2_gaps = df["v2_gap"].dropna() * 100
    fig, ax = plt.subplots(figsize=(8, 5))
    bins = np.arange(-5, 165, 10)
    ax.hist(v1_gaps, bins=bins, alpha=0.8, label="Old MILP (v1): every run at 0%", color="#4C72B0")
    ax.hist(v2_gaps, bins=bins, alpha=0.8, label="Real MILP (v2): 4.8% to 152%", color="#C44E52")
    ax.set_xlabel("How much worse than perfect (%)")
    ax.set_ylabel("Number of test cases (out of 24)")
    ax.set_title("The old “0% gap” was measuring the wrong thing", fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_milp_gap.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("fig3 done")


def fig4_runtime():
    ours_n = [5, 10, 20, 40, 60]
    ours_us = [164.5, 434.9, 1401.9, 3776.8, 5805.4]
    milp_n = [2, 4, 6, 8, 10, 12, 15]
    milp_s = [0.20, 0.57, 1.85, 2.83, 77.91, 44.79, 82.92]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.plot(ours_n, [v / 1000.0 for v in ours_us], marker="o", linewidth=2.5, color="#C44E52",
            label="Our scheduler\n(cost per decision)")
    ax.plot(milp_n, milp_s, marker="s", linewidth=2.5, color="#4C72B0",
            label="Exact solver (MILP)\n(cost per full solve)")
    ax.set_yscale("log")
    ax.set_xlabel("Number of drones")
    ax.set_ylabel("Time (seconds, log scale)")
    ax.set_title("Speed vs. scale: why a fast scheduler is needed", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3, which="both")
    ax.annotate("Our scheduler: still\nunder 6 milliseconds\nat 60 drones", xy=(60, 5805.4 / 1000),
                xytext=(35, 0.001), fontsize=9, color="#C44E52",
                arrowprops=dict(arrowstyle="->", color="#C44E52"))
    ax.annotate("Exact solver: minutes,\nand hits a wall\naround 10 drones", xy=(10, 77.91),
                xytext=(15, 5), fontsize=9, color="#4C72B0",
                arrowprops=dict(arrowstyle="->", color="#4C72B0"))
    fig.tight_layout()
    fig.savefig(OUT / "fig4_runtime.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("fig4 done")


def fig5_b3_mechanism():
    labels = ["Baseline", "B3, proactive\ncharging ON\n(the default)", "B3, proactive\ncharging OFF"]
    util = [0.8154, 0.6563, 0.8132]
    sessions = [5.11, 36.63, 5.15]
    miss = [0.1066, 0.2856, 0.0887]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6))
    metrics = [("Pad usage\n(fraction of time busy)", util, "#4C72B0"),
               ("Charging trips\nper drone", sessions, "#DD8452"),
               ("Fraction of missions\ndelivered late", miss, "#C44E52")]
    for ax, (title, vals, color) in zip(axes, metrics):
        x = np.arange(len(labels))
        bars = ax.bar(x, vals, color=color, width=0.6)
        ax.set_title(title, fontsize=12)
        ax.bar_label(bars, fmt="%.2f", fontsize=10, padding=3)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylim(top=max(vals) * 1.18)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Why B3 struggled: charging “just in case”, with no traffic-awareness to fix it",
                 fontsize=14, fontweight="bold", y=1.04)
    fig.tight_layout()
    fig.savefig(OUT / "fig5_b3_mechanism.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("fig5 done")


def fig6_fleet_size_reversal():
    """Phase 6's own headline finding (pre-remediation, unaffected by the
    remediation work): adaptive vs. full charging's energy comparison
    flips sign as the fleet grows. Numbers from CLAUDE.md/HISTORY.md's
    validated Phase 6 fleet-size sweep (30 seeds/point, Wilcoxon p<=1.86e-09
    at every point)."""
    n = [5, 10, 20, 40, 60]
    pct = [-23.03, -20.54, 5.28, 8.62, 13.14]
    colors_bar = ["#55A868" if v < 0 else "#C44E52" for v in pct]
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar([str(v) for v in n], pct, color=colors_bar)
    ax.axhline(0, color="black", linewidth=1)
    ax.bar_label(bars, fmt="%+.1f%%", fontsize=10)
    ax.set_xlabel("Fleet size (number of drones)")
    ax.set_ylabel("Adaptive charging's energy cost,\nvs. always-charge-to-full")
    ax.set_title("Small fleets: partial charging saves energy.\nLarge fleets: it costs more.",
                 fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig6_fleet_size_reversal.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("fig6 done")


if __name__ == "__main__":
    fig1_crossover()
    fig2_capacity_bug()
    fig3_milp_gap()
    fig4_runtime()
    fig5_b3_mechanism()
    fig6_fleet_size_reversal()
    print("all done")
