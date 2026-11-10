#!/usr/bin/env python3
"""Aggregate results/*.csv and plot 5 metrics x 2 scenarios (like Fig. 4-13).

Install deps (Ubuntu):
    sudo apt install -y python3-pandas python3-matplotlib python3-scipy
Run from the ns-3 root:
    python3 analyze.py
"""
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

try:
    from scipy import stats
except ImportError:
    stats = None

files = glob.glob("results/*.csv")
if not files:
    raise SystemExit("No CSV files found in results/. Run run_all.sh first.")

df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
df["pdr_over_100"] = df["pdr_percent"] / 100.0  # what the paper calls "NRL"
df.to_csv("all_runs.csv", index=False)

METRICS = [
    ("throughput_kbps", "Throughput (Kbps)"),
    ("pdr_percent", "Packet delivery ratio (%)"),
    ("delay_ms", "End-to-end delay (ms)"),
    ("loss_packets", "Packet loss (packets)"),
    ("nrl", "Normalized routing load (routing pkts / data pkts received)"),
]
SCENARIOS = [("SS-I", "nodes", "Number of nodes"), ("SS-II", "pause", "Pause time (s)")]
STYLE = {"OLSR": ("tab:green", "^"), "AODV": ("tab:blue", "o"), "DSDV": ("tab:red", "s")}


def ci95(series):
    n = series.count()
    if n < 2:
        return 0.0
    sem = series.std(ddof=1) / (n ** 0.5)
    t = stats.t.ppf(0.975, n - 1) if stats else 1.96
    return t * sem


os.makedirs("plots", exist_ok=True)
summary_rows = []

for scen, xcol, xlabel in SCENARIOS:
    sub = df[df["scenario"] == scen]
    if sub.empty:
        continue
    for col, ylabel in METRICS:
        fig, ax = plt.subplots(figsize=(6, 4))
        for proto, (color, marker) in STYLE.items():
            g = sub[sub["protocol"] == proto].groupby(xcol)[col]
            mean, err = g.mean(), g.apply(ci95)
            if mean.empty:
                continue
            ax.errorbar(mean.index, mean.values, yerr=err.values, label=proto,
                        color=color, marker=marker, capsize=3)
            for x in mean.index:
                summary_rows.append((scen, proto, x, col, mean[x], err[x]))
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{scen}: {col}")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(f"plots/{scen}_{col}.png", dpi=150)
        plt.close(fig)

pd.DataFrame(summary_rows,
             columns=["scenario", "protocol", "x", "metric", "mean", "ci95"]
             ).to_csv("summary.csv", index=False)
print("Wrote all_runs.csv, summary.csv and plots/*.png "
      f"({len(df)} runs, {df['run'].nunique()} seeds).")
