#!/usr/bin/env python3
"""Aggregate MANET simulation CSV files and generate paper-comparison plots.

Run from the ns-3 root directory:
    python3 analyze.py

Optional environment variables:
    RESULTS_DIR=results OUT_DIR=. python3 analyze.py

Main analysis:
- Uses exactly seeds 1..6 for all 42 experimental settings (252 runs).
- Any additional runs (e.g. seeds 7..10) are archived in all_runs.csv but
  excluded from the main averages. They do NOT abort the analysis, so the
  scripts in this repository can be used with their default seed range
  without producing a dataset that this script rejects.
- Uses formula-based measured NRL = routing_packets / recv as the main NRL,
  plus nrl_origin = routing_packets_origin / recv when the column is present.
- Keeps PDR/100 separately because the original paper's NRL tables equal
  PDR/100 exactly; they are not a measured routing load.
- Emits paper_comparison.csv, which places the simulation means next to the
  values printed in the paper's Tables 2-6 and 8-12.

NOTE on the paper's tables: throughput, packet loss and NRL in the original
paper are all algebraic functions of PDR (throughput = 20 * PDR/100,
loss = 6000 * (1 - PDR/100), NRL = PDR/100), so only PDR and EED are
independent measurements. paper_comparison.csv marks this explicitly.
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

# Columns that every simulation CSV must provide.
REQUIRED_COLUMNS = [
    "scenario", "protocol", "nodes", "pause", "run",
    "sent", "recv", "pdr_percent",
    "throughput_kbps", "delay_ms", "loss_packets",
    "routing_packets", "routing_bytes", "nrl",
]

# Columns that newer runs add; everything degrades gracefully without them.
OPTIONAL_COLUMNS = [
    "sent_accepted", "routing_packets_origin", "nrl_origin",
    "sim_time_s", "payload_bytes",
]

PROTOCOLS = ["OLSR", "DSDV", "AODV"]
# PROTOCOLS is ordered for plotting/legend consistency, but the paper tables
# below are transcribed in the column order (AODV, DSDV, OLSR). Keep an explicit
# mapping so the two orders can never be confused. (An earlier version indexed
# the tuples with enumerate(PROTOCOLS), which silently compared OLSR against
# AODV's paper values.)
PAPER_COLUMN_ORDER = ("AODV", "DSDV", "OLSR")
SS1_NODES = [30, 40, 50, 60, 70, 80, 90, 100]
SS2_PAUSES = [5, 10, 15, 20, 25, 30]
MAIN_SEEDS = set(range(1, 7))

# Fallbacks used only when a CSV predates the sim_time_s / payload_bytes columns.
SIM_TIME_SECONDS = 150
UDP_PAYLOAD_BYTES = 64

MAIN_METRICS = [
    ("throughput_kbps", "Throughput (Kbps)"),
    ("pdr_percent", "Packet delivery ratio (%)"),
    ("delay_ms", "End-to-end delay (ms)"),
    ("loss_packets", "Packet loss (packets)"),
    ("nrl_measured", "Normalized routing load (per-hop)"),
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

# ---------------------------------------------------------------------------
# Values transcribed from the original paper (IJCNIS 8(12), 2016).
# Order in every tuple is (AODV, DSDV, OLSR).
#
# In Tables 8-12 the PDF renders the "5" pause label glued to the first
# value (e.g. "514.42" is pause 5 -> AODV 14.42), so those were split by hand.
# ---------------------------------------------------------------------------
PAPER_SS1 = {
    "throughput_kbps": {
        30: (16.04, 14.95, 18.27), 40: (17.93, 14.30, 16.93),
        50: (14.47, 12.64, 17.99), 60: (1.87, 14.87, 18.91),
        70: (9.73, 14.58, 18.99), 80: (11.62, 15.60, 18.60),
        90: (0.68, 13.47, 17.47), 100: (1.42, 13.58, 18.45),
    },
    "pdr_percent": {
        30: (80.22, 74.73, 91.33), 40: (89.63, 71.52, 84.67),
        50: (72.33, 63.22, 89.93), 60: (9.35, 74.35, 94.55),
        70: (48.63, 72.88, 94.97), 80: (58.08, 77.98, 93.00),
        90: (3.42, 67.33, 87.37), 100: (7.08, 67.88, 92.25),
    },
    "delay_ms": {
        30: (6.17, 8.45, 2.37), 40: (2.89, 9.96, 4.53),
        50: (9.56, 14.55, 2.80), 60: (242.38, 8.62, 1.44),
        70: (26.41, 9.30, 1.33), 80: (18.04, 7.06, 1.88),
        90: (706.71, 12.13, 3.62), 100: (327.94, 11.83, 2.10),
    },
    "loss_packets": {
        30: (1187, 1516, 520), 40: (622, 1709, 920),
        50: (1660, 2207, 604), 60: (5439, 1539, 327),
        70: (3082, 1627, 302), 80: (2515, 1321, 420),
        90: (5795, 1960, 758), 100: (5575, 1927, 465),
    },
    "nrl": {
        30: (0.802, 0.747, 0.913), 40: (0.896, 0.715, 0.847),
        50: (0.723, 0.632, 0.899), 60: (0.094, 0.744, 0.946),
        70: (0.486, 0.729, 0.950), 80: (0.581, 0.780, 0.930),
        90: (0.034, 0.673, 0.874), 100: (0.071, 0.679, 0.923),
    },
}

PAPER_SS2 = {
    "throughput_kbps": {
        5: (2.88, 12.96, 17.91), 10: (5.20, 13.25, 17.80),
        15: (13.55, 14.31, 17.48), 20: (16.27, 12.75, 18.74),
        25: (16.42, 12.21, 18.69), 30: (14.21, 12.76, 18.27),
    },
    "pdr_percent": {
        5: (14.42, 64.82, 89.55), 10: (25.98, 66.23, 89.02),
        15: (67.77, 71.53, 87.40), 20: (81.37, 63.73, 93.72),
        25: (82.10, 61.03, 93.45), 30: (71.07, 63.78, 91.35),
    },
    "delay_ms": {
        5: (148.41, 13.57, 2.92), 10: (71.22, 12.75, 3.08),
        15: (11.89, 9.95, 3.60), 20: (5.73, 14.23, 1.68),
        25: (5.45, 15.96, 1.75), 30: (10.18, 14.20, 2.37),
    },
    "loss_packets": {
        5: (5135, 2111, 627), 10: (4441, 2026, 659),
        15: (1934, 1708, 756), 20: (1118, 2176, 377),
        25: (1074, 2338, 393), 30: (1736, 2173, 519),
    },
    "nrl": {
        5: (0.144, 0.648, 0.896), 10: (0.260, 0.662, 0.890),
        15: (0.678, 0.715, 0.874), 20: (0.814, 0.637, 0.937),
        25: (0.821, 0.610, 0.935), 30: (0.711, 0.638, 0.914),
    },
}

# Metrics whose paper values are pure algebra on PDR rather than measurements.
DERIVED_IN_PAPER = {"throughput_kbps", "loss_packets", "nrl"}


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

        missing_columns = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
        if missing_columns:
            problems.append((filename, f"Missing columns: {missing_columns}"))
            continue

        keep = REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in frame.columns]
        frames.append(frame[keep].copy())

    if problems:
        details = "\n".join(f"  {name}: {reason}" for name, reason in problems)
        stop(f"{len(problems)} CSV file(s) could not be used:\n{details}")

    if not frames:
        stop("No valid CSV files were found.")

    df = pd.concat(frames, ignore_index=True, sort=False)

    # Columns that every file must provide.
    required_numeric = [
        "nodes", "pause", "run", "sent", "recv", "pdr_percent",
        "throughput_kbps", "delay_ms", "loss_packets",
        "routing_packets", "routing_bytes", "nrl",
    ]
    # Optional columns may be absent from some files. Concatenating an old file
    # (without them) with a new one (with them) fills NaN, so an optional column
    # is only usable if it is populated for every row; otherwise it is dropped.
    for column in OPTIONAL_COLUMNS:
        if column not in df.columns:
            continue
        df[column] = pd.to_numeric(df[column], errors="coerce")
        if df[column].isna().any():
            print(f"NOTE: optional column {column!r} is only partially present "
                  "(mixed CSV versions); it is ignored.")
            df = df.drop(columns=[column])

    for column in required_numeric:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[required_numeric].isna().any().any():
        bad_rows = df[df[required_numeric].isna().any(axis=1)]
        stop(
            "CSV data contains missing or non-numeric values. "
            f"First problematic rows:\n{bad_rows.head().to_string(index=False)}"
        )

    if not set(df["protocol"].unique()).issubset(set(PROTOCOLS)):
        stop(f"Unexpected protocol names: {sorted(set(df['protocol']) - set(PROTOCOLS))}")

    # The setting keys are integers in the paper's design. Normalise them so a
    # CSV that recorded "0.0" instead of "0" still matches the expected tuples.
    for column in ("nodes", "pause", "run"):
        values = pd.to_numeric(df[column], errors="coerce").astype("float64")
        if values.isna().any():
            stop(f"Column {column!r} contains missing values.")
        as_int = values.round().astype("int64")
        if float((values - as_int).abs().max()) > 1e-9:
            stop(f"Column {column!r} contains non-integer values.")
        df[column] = as_int

    key_columns = ["scenario", "protocol", "nodes", "pause", "run"]
    before = len(df)
    df = df.drop_duplicates(subset=key_columns, keep="last").copy()
    duplicates_removed = before - len(df)
    if duplicates_removed:
        print(f"NOTE: removed {duplicates_removed} duplicate run row(s); kept the last row.")

    return df, len(files)


def validate_dataset(df):
    """Validate the main (seeds 1..6) part; tolerate extra runs."""
    expected_settings = expected_main_settings()
    main = df[df["run"].isin(MAIN_SEEDS)].copy()
    group_columns = ["scenario", "protocol", "nodes", "pause"]

    observed_settings = set(
        main[["scenario", "protocol", "nodes", "pause"]]
        .itertuples(index=False, name=None)
    )

    missing_settings = expected_settings - observed_settings
    if missing_settings:
        print("Missing main settings:")
        for item in sorted(missing_settings):
            print(" ", item)
        stop("The main dataset does not cover all 42 expected settings.")

    unexpected_settings = observed_settings - expected_settings
    if unexpected_settings:
        print(f"NOTE: {len(unexpected_settings)} setting(s) are outside the paper's "
              "design and are ignored in the per-setting tables:")
        for item in sorted(unexpected_settings):
            print(" ", item)
        keep_mask = main[group_columns].apply(tuple, axis=1).isin(expected_settings)
        main = main[keep_mask].copy()

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

    if len(main) != 42 * len(MAIN_SEEDS):
        stop(f"Expected {42 * len(MAIN_SEEDS)} main rows, found {len(main)}.")

    extras = df[~df["run"].isin(MAIN_SEEDS)]
    if len(extras):
        print(f"NOTE: {len(extras)} additional run(s) (seeds outside 1..6) are "
              "archived in all_runs.csv but excluded from the main averages.")

    print("Dataset validation: OK")
    print(f"  Unique result rows: {len(df)}")
    print(f"  Main analysis rows: {len(main)} (42 settings x {len(MAIN_SEEDS)} seeds)")
    print(f"  Additional rows archived: {len(extras)}")
    return main


def recalculate_metrics(df):
    """Recalculate metrics from per-run counters where the required data exists."""
    result = df.copy()

    # Use the run's own time window and payload size when the CSV provides them,
    # so changing --totalTime or --packetSize does not silently corrupt the
    # throughput calculation.
    if "sim_time_s" in result.columns:
        sim_time = result["sim_time_s"]
    else:
        sim_time = SIM_TIME_SECONDS
    if "payload_bytes" in result.columns:
        payload = result["payload_bytes"]
    else:
        payload = UDP_PAYLOAD_BYTES

    result["throughput_kbps"] = result["recv"] * payload * 8 / (sim_time * 1024)

    result["pdr_percent"] = np.where(
        result["sent"] > 0,
        result["recv"] / result["sent"] * 100,
        np.nan,
    )
    # `sent` is a formula in the simulator; recv can exceed it by a packet or two.
    over = result["recv"] > result["sent"]
    if over.any():
        print(f"NOTE: {int(over.sum())} run(s) have recv > sent; PDR clamped to 100% "
              "and loss clamped to 0. `sent` is derived from the CBR schedule.")
    result["pdr_percent"] = result["pdr_percent"].clip(upper=100.0)
    result["loss_packets"] = (result["sent"] - result["recv"]).clip(lower=0)

    result["nrl_measured"] = np.where(
        result["recv"] > 0,
        result["routing_packets"] / result["recv"],
        np.nan,
    )

    if "routing_packets_origin" in result.columns:
        result["nrl_origin"] = np.where(
            result["recv"] > 0,
            result["routing_packets_origin"] / result["recv"],
            np.nan,
        )

    # Retained only for a diagnostic comparison with the values tabulated as
    # NRL in the original paper (which equal PDR / 100).
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
        errors = grouped.apply(ci95)

        if means.empty:
            stop(f"No {protocol} data for {scenario}, metric {metric_column}.")

        color, marker = STYLE[protocol]
        ax.errorbar(
            means.index,
            means.values,
            yerr=errors.values,
            label=protocol,
            color=color,
            marker=marker,
            linewidth=1.5,
            capsize=3,
        )

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(f"{scenario}: {metric_column}")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def build_paper_comparison(df):
    """Place simulated means next to the values printed in the paper tables."""
    rows = []
    for scenario, x_column, _ in SCENARIOS:
        paper_tables = PAPER_SS1 if scenario == "SS-I" else PAPER_SS2
        subset = df[df["scenario"] == scenario]

        for metric_column in ["throughput_kbps", "pdr_percent", "delay_ms",
                              "loss_packets", "nrl"]:
            table = paper_tables[metric_column]

            # The paper's NRL column is PDR/100, not a routing load. To keep the
            # comparison apples-to-apples we compare it against the same algebra
            # recomputed from this simulation's PDR, and additionally report the
            # two real routing-load measurements in their own columns.
            sim_metric = "nrl_pdr_over_100" if metric_column == "nrl" else metric_column

            for x_value, values in table.items():
                x_int = int(x_value)
                paper_by_protocol = dict(zip(PAPER_COLUMN_ORDER, values))
                for protocol in PROTOCOLS:
                    rows_here = subset[
                        (subset["protocol"] == protocol)
                        & (subset[x_column].astype(int) == x_int)
                    ]
                    sim = rows_here[sim_metric]

                    if sim.empty:
                        continue

                    paper_value = paper_by_protocol[protocol]
                    sim_mean = float(sim.mean())
                    rows.append(
                        (
                            scenario,
                            protocol,
                            x_int,
                            metric_column,
                            paper_value,
                            sim_mean,
                            sim_mean - paper_value,
                            ci95(sim),
                            int(sim.count()),
                            metric_column in DERIVED_IN_PAPER,
                            float(rows_here["nrl_measured"].mean())
                            if metric_column == "nrl" else np.nan,
                            float(rows_here["nrl_origin"].mean())
                            if metric_column == "nrl" and "nrl_origin" in rows_here
                            else np.nan,
                        )
                    )

    comparison = pd.DataFrame(
        rows,
        columns=[
            "scenario", "protocol", "x", "metric", "paper_value",
            "sim_mean", "delta", "sim_ci95", "n_runs",
            "paper_value_is_derived_from_pdr",
            "sim_nrl_measured", "sim_nrl_origin",
        ],
    )
    comparison.to_csv(os.path.join(OUT_DIR, "paper_comparison.csv"), index=False)

    note = (
        "paper_value_is_derived_from_pdr: True means the paper's column is an\n"
        "algebraic function of PDR rather than an independent measurement\n"
        "(throughput = 20 * PDR/100, loss = 6000 * (1 - PDR/100), NRL = PDR/100).\n"
        "For those rows the comparison only checks that the algebra reproduces.\n"
    )
    with open(os.path.join(OUT_DIR, "paper_comparison_README.txt"), "w") as handle:
        handle.write(note)

    return comparison


def build_summaries_and_plots(df):
    os.makedirs(OUT_DIR, exist_ok=True)
    plot_dir = os.path.join(OUT_DIR, "plots")
    diagnostic_dir = os.path.join(OUT_DIR, "plots_nrl_pdr_over_100")
    origin_dir = os.path.join(OUT_DIR, "plots_nrl_origin")
    os.makedirs(plot_dir, exist_ok=True)
    os.makedirs(diagnostic_dir, exist_ok=True)

    summary_rows = []
    diagnostic_rows = []

    for scenario, x_column, x_label in SCENARIOS:
        subset = df[df["scenario"] == scenario]
        if subset.empty:
            stop(f"No data found for {scenario}.")

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

        # Originated-only NRL, comparable with published results.
        if "nrl_origin" in subset.columns:
            os.makedirs(origin_dir, exist_ok=True)
            make_plot(
                subset, scenario, x_column, x_label,
                "nrl_origin",
                "Normalized routing load (originated only)",
                os.path.join(origin_dir, f"{scenario}_nrl_origin.png"),
            )
            for protocol in PROTOCOLS:
                protocol_data = subset[subset["protocol"] == protocol]
                grouped = protocol_data.groupby(x_column)["nrl_origin"]
                for x_value, values in grouped:
                    summary_rows.append(
                        (
                            scenario,
                            protocol,
                            x_value,
                            "nrl_origin",
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
    print("  all_runs.csv                  - every unique run found")
    print("  analysis_runs.csv             - main runs, recalculated metrics")
    print("  summary.csv                   - main metrics x 2 scenarios, with CI95")
    print("  paper_comparison.csv          - simulation mean vs. paper table values")
    print("  summary_nrl_pdr_over_100.csv  - separate diagnostic, not measured NRL")
    print("  plots/                        - main comparison plots (with error bars)")
    print("  plots_nrl_origin/             - NRL counted at the originating node")
    print("  plots_nrl_pdr_over_100/       - diagnostic plots")


def main():
    df_all, file_count = load_results()
    print(f"CSV files read: {file_count}")

    os.makedirs(OUT_DIR, exist_ok=True)
    df_all.to_csv(os.path.join(OUT_DIR, "all_runs.csv"), index=False)

    df_main = validate_dataset(df_all)
    df_main = recalculate_metrics(df_main)
    df_main.to_csv(os.path.join(OUT_DIR, "analysis_runs.csv"), index=False)

    print(f"Main analysis: {len(df_main)} runs, {len(MAIN_SEEDS)} seeds per setting.")
    print("Main NRL uses routing_packets / recv (per hop); nrl_origin is reported too.")
    print("PDR/100 is kept separately as a diagnostic comparison with the paper tables.")

    build_summaries_and_plots(df_main)
    build_paper_comparison(df_main)


if __name__ == "__main__":
    main()
