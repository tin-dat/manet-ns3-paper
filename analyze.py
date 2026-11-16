#!/usr/bin/env python3
"""Aggregate MANET simulation CSV files and generate paper-comparison plots.

Run from the ns-3 root directory:
    python3 analyze.py

Optional environment variables:
    RESULTS_DIR=results OUT_DIR=. python3 analyze.py

Main analysis:
- Uses exactly seeds 1..6 for all 42 experimental settings (252 runs).
- Archives the 12 additional OLSR runs (seeds 7..10 at 30, 40, 50 nodes)
  in all_runs.csv, but excludes them from the main averages.
- Uses formula-based measured NRL = routing_packets / recv as the main NRL.
- Keeps PDR/100 separately because the original paper's NRL tables appear
  numerically inconsistent with the NRL formula stated in its methodology.
"""

import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from scipy import stats
except ImportError:
    stats = None


RES_DIR = os.environ.get("RESULTS_DIR", "results")
OUT_DIR = os.environ.get("OUT_DIR", ".")

EXPECTED_COLUMNS = [
    "scenario", "protocol", "nodes", "pause", "run",
    "sent", "sent_accepted", "recv", "pdr_percent",
    "throughput_kbps", "delay_ms", "loss_packets",
    "routing_packets", "routing_bytes", "nrl",
]

PROTOCOLS = ["OLSR", "DSDV", "AODV"]
SS1_NODES = [30, 40, 50, 60, 70, 80, 90, 100]
SS2_PAUSES = [5, 10, 15, 20, 25, 30]
MAIN_SEEDS = set(range(1, 7))

# Fixed application/simulation parameters used for this experiment.
SIM_TIME_SECONDS = 150
UDP_PAYLOAD_BYTES = 64

# Five main metrics. NRL is calculated from the formula in the paper.
MAIN_METRICS = [
    ("throughput_kbps", "Throughput (Kbps)"),
    ("pdr_percent", "Packet delivery ratio (%)"),
    ("delay_ms", "End-to-end delay (ms)"),
    ("loss_packets", "Packet loss (packets)"),
    ("nrl_measured", "Normalized routing load"),
]

STYLE = {
    "AODV": ("tab:blue", "o"),
    "DSDV": ("tab:red", "s"),
    "OLSR": ("tab:green", "^"),
}

SCENARIOS = [
    ("SS-I", "nodes", "Number of nodes"),
    ("SS-II", "pause", "Pause time (s)"),
]


def stop(message):
    raise SystemExit(f"ERROR: {message}")


def ci95(series):
    """Return the two-sided 95% confidence-interval half-width."""
    values = pd.to_numeric(series, errors="coerce").dropna()
    n = len(values)
    if n < 2:
        return 0.0

    sem = values.std(ddof=1) / np.sqrt(n)
    critical_value = stats.t.ppf(0.975, n - 1) if stats else 1.96
    return float(critical_value * sem)


def expected_main_settings():
    """Return the 42 expected (scenario, protocol, nodes, pause) groups."""
    settings = set()
    for protocol in PROTOCOLS:
        for nodes in SS1_NODES:
            settings.add(("SS-I", protocol, nodes, 0))
        for pause in SS2_PAUSES:
            settings.add(("SS-II", protocol, 50, pause))
    return settings


def load_results():
    # Only read simulation result files, not generated summary/debug CSVs.
    files = sorted(glob.glob(os.path.join(RES_DIR, "SS-*.csv")))
    if not files:
        stop(f"No SS-*.csv files found in {RES_DIR!r}.")

    frames = []
    problems = []

    for filename in files:
        try:
            frame = pd.read_csv(filename)
        except Exception as exc:
            problems.append((filename, str(exc)))
            continue

        missing_columns = [c for c in EXPECTED_COLUMNS if c not in frame.columns]
        if missing_columns:
            problems.append((filename, f"Missing columns: {missing_columns}"))
            continue

        frames.append(frame[EXPECTED_COLUMNS].copy())

    if problems:
        details = "\n".join(f"  {name}: {reason}" for name, reason in problems)
        stop(f"{len(problems)} CSV file(s) could not be used:\n{details}")

    if not frames:
        stop("No valid CSV files were found.")

    df = pd.concat(frames, ignore_index=True)

    numeric_columns = [
        "nodes", "pause", "run", "sent", "sent_accepted", "recv",
        "pdr_percent", "throughput_kbps", "delay_ms", "loss_packets",
        "routing_packets", "routing_bytes", "nrl",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[numeric_columns].isna().any().any():
        bad_rows = df[df[numeric_columns].isna().any(axis=1)]
        stop(
            "CSV data contains missing or non-numeric values. "
            f"First problematic rows:\n{bad_rows.head().to_string(index=False)}"
        )

    if not set(df["protocol"].unique()).issubset(set(PROTOCOLS)):
        stop(f"Unexpected protocol names: {sorted(set(df['protocol']) - set(PROTOCOLS))}")

    key_columns = ["scenario", "protocol", "nodes", "pause", "run"]
    before = len(df)
    df = df.drop_duplicates(subset=key_columns, keep="last").copy()
    duplicates_removed = before - len(df)
    if duplicates_removed:
        print(f"NOTE: removed {duplicates_removed} duplicate run row(s); kept the last row.")

    return df, len(files)


def validate_dataset(df):
    expected_settings = expected_main_settings()
    main = df[df["run"].isin(MAIN_SEEDS)].copy()

    observed_settings = set(
        main[["scenario", "protocol", "nodes", "pause"]]
        .itertuples(index=False, name=None)
    )

    missing_settings = expected_settings - observed_settings
    unexpected_settings = observed_settings - expected_settings
    if missing_settings or unexpected_settings:
        if missing_settings:
            print("Missing main settings:")
            for item in sorted(missing_settings):
                print(" ", item)
        if unexpected_settings:
            print("Unexpected main settings:")
            for item in sorted(unexpected_settings):
                print(" ", item)
        stop("The main dataset does not match the expected 42 settings.")

    group_columns = ["scenario", "protocol", "nodes", "pause"]
    run_sets = main.groupby(group_columns)["run"].apply(
        lambda values: set(values.astype(int))
    )
    bad_groups = {
        key: sorted(run_set)
        for key, run_set in run_sets.items()
        if run_set != MAIN_SEEDS
    }
    if bad_groups:
        print("Settings that do not contain exactly seeds 1..6:")
        for key, runs in bad_groups.items():
            print(f"  {key}: seeds {runs}")
        stop("Every main setting must contain exactly seeds 1..6.")

    if len(main) != 252:
        stop(f"Expected 252 main rows, found {len(main)}.")

    extras = df[~df["run"].isin(MAIN_SEEDS)].copy()
    expected_extras = {
        ("SS-I", "OLSR", nodes, 0, run)
        for nodes in (30, 40, 50)
        for run in (7, 8, 9, 10)
    }
    observed_extras = set(
        extras[["scenario", "protocol", "nodes", "pause", "run"]]
        .itertuples(index=False, name=None)
    )

    if observed_extras != expected_extras:
        missing = expected_extras - observed_extras
        unexpected = observed_extras - expected_extras
        if missing:
            print("Missing additional OLSR runs:")
            for item in sorted(missing):
                print(" ", item)
        if unexpected:
            print("Unexpected additional runs:")
            for item in sorted(unexpected):
                print(" ", item)
        stop("The additional runs do not match the expected 12 OLSR runs.")

    if len(df) != 264:
        stop(f"Expected 264 unique result rows, found {len(df)}.")

    print("Dataset validation: OK")
    print(f"  Unique result rows: {len(df)}")
    print(f"  Main analysis rows: {len(main)} (42 settings x 6 seeds)")
    print(f"  Additional OLSR rows archived: {len(extras)}")
    return main


def recalculate_metrics(df):
    """Recalculate metrics from per-run counters where the required data exists."""
    result = df.copy()

    # Payload throughput at the application receiver.
    result["throughput_kbps"] = (
        result["recv"] * UDP_PAYLOAD_BYTES * 8
        / (SIM_TIME_SECONDS * 1024)
    )

    # 'sent' is the generated CBR packet count in this simulation.
    result["pdr_percent"] = np.where(
        result["sent"] > 0,
        result["recv"] / result["sent"] * 100,
        np.nan,
    )
    result["loss_packets"] = result["sent"] - result["recv"]

    # Formula-based NRL from the paper's stated definition.
    result["nrl_measured"] = np.where(
        result["recv"] > 0,
        result["routing_packets"] / result["recv"],
        np.nan,
    )

    # Retained only for a separate diagnostic comparison with the values
    # tabulated as NRL in the original paper (which appear to equal PDR / 100).
    result["nrl_pdr_over_100"] = result["pdr_percent"] / 100.0

    if result[["throughput_kbps", "pdr_percent", "loss_packets"]].isna().any().any():
        stop("Metric recalculation produced invalid values.")

    if result["nrl_measured"].isna().any():
        stop("At least one run has recv=0; measured NRL cannot be calculated.")

    return result


def make_plot(subset, scenario, x_column, x_label, metric_column, y_label, output_path):
    fig, ax = plt.subplots(figsize=(6, 4))

    for protocol in PROTOCOLS:
        protocol_data = subset[subset["protocol"] == protocol]
        grouped = protocol_data.groupby(x_column)[metric_column]
        means = grouped.mean()

        if means.empty:
            stop(f"No {protocol} data for {scenario}, metric {metric_column}.")

        color, marker = STYLE[protocol]
        ax.plot(
            means.index,
            means.values,
            label=protocol,
            color=color,
            marker=marker,
            linewidth=1.5,
        )

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(f"{scenario}: {metric_column}")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def build_summaries_and_plots(df):
    os.makedirs(OUT_DIR, exist_ok=True)
    plot_dir = os.path.join(OUT_DIR, "plots")
    diagnostic_dir = os.path.join(OUT_DIR, "plots_nrl_pdr_over_100")
    os.makedirs(plot_dir, exist_ok=True)
    os.makedirs(diagnostic_dir, exist_ok=True)

    summary_rows = []
    diagnostic_rows = []

    for scenario, x_column, x_label in SCENARIOS:
        subset = df[df["scenario"] == scenario]
        if subset.empty:
            stop(f"No data found for {scenario}.")

        # Five main metrics, with formula-based measured NRL as the fifth.
        for metric_column, y_label in MAIN_METRICS:
            make_plot(
                subset, scenario, x_column, x_label,
                metric_column, y_label,
                os.path.join(plot_dir, f"{scenario}_{metric_column}.png"),
            )

            for protocol in PROTOCOLS:
                protocol_data = subset[subset["protocol"] == protocol]
                grouped = protocol_data.groupby(x_column)[metric_column]

                for x_value, values in grouped:
                    summary_rows.append(
                        (
                            scenario,
                            protocol,
                            x_value,
                            metric_column,
                            float(values.mean()),
                            ci95(values),
                            int(values.count()),
                        )
                    )

        # Separate diagnostic: PDR/100 is not formula-based NRL.
        make_plot(
            subset, scenario, x_column, x_label,
            "nrl_pdr_over_100",
            "PDR / 100 (diagnostic; not measured NRL)",
            os.path.join(diagnostic_dir, f"{scenario}_pdr_over_100.png"),
        )

        for protocol in PROTOCOLS:
            protocol_data = subset[subset["protocol"] == protocol]
            grouped = protocol_data.groupby(x_column)["nrl_pdr_over_100"]
            for x_value, values in grouped:
                diagnostic_rows.append(
                    (
                        scenario,
                        protocol,
                        x_value,
                        float(values.mean()),
                        ci95(values),
                        int(values.count()),
                    )
                )

    summary = pd.DataFrame(
        summary_rows,
        columns=["scenario", "protocol", "x", "metric", "mean", "ci95", "n_runs"],
    )
    summary.to_csv(os.path.join(OUT_DIR, "summary.csv"), index=False)

    diagnostic_summary = pd.DataFrame(
        diagnostic_rows,
        columns=["scenario", "protocol", "x", "mean", "ci95", "n_runs"],
    )
    diagnostic_summary.to_csv(
        os.path.join(OUT_DIR, "summary_nrl_pdr_over_100.csv"), index=False
    )

    print("Output files created:")
    print("  all_runs.csv                  - all 264 unique runs")
    print("  analysis_runs.csv             - 252 main runs, recalculated metrics")
    print("  summary.csv                   - 5 main metrics x 2 scenarios")
    print("  summary_nrl_pdr_over_100.csv  - separate diagnostic, not measured NRL")
    print("  plots/                        - 10 main comparison plots")
    print("  plots_nrl_pdr_over_100/       - 2 diagnostic plots")


def main():
    df_all, file_count = load_results()
    print(f"CSV files read: {file_count}")

    os.makedirs(OUT_DIR, exist_ok=True)
    df_all.to_csv(os.path.join(OUT_DIR, "all_runs.csv"), index=False)

    df_main = validate_dataset(df_all)
    df_main = recalculate_metrics(df_main)
    df_main.to_csv(os.path.join(OUT_DIR, "analysis_runs.csv"), index=False)

    print("Main analysis: 252 runs, six seeds per setting.")
    print("The 12 additional OLSR runs are archived but excluded from main averages.")
    print("Main NRL uses routing_packets / recv, as defined in the paper.")
    print("PDR/100 is kept separately as a diagnostic comparison with the paper tables.")

    build_summaries_and_plots(df_main)


if __name__ == "__main__":
    main()
