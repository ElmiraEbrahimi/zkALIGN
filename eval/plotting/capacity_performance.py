"""Validate saved capacity repetitions and draw time/memory without rerunning them."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .draw import plt


BOUNDS = (32, 64, 128, 256, 384)
STAGES = ("compile", "setup", "witness", "prove", "verify")
SERIES = (
    ("compile", "Compilation", "#2171b5", "o", "-"),
    ("setup", "Setup", "#8c2d26", "s", "--"),
    ("witness", "Input-witness encoding", "#54278f", "^", ":"),
    ("prove", "Proof generation", "#005a32", "D", "-."),
)


def validate(runs, summary):
    keys = ["alignment_capacity", "stage", "repeat"]
    expected = {(b, s, r) for b in BOUNDS for s in STAGES for r in range(1, 6)}
    if runs.duplicated(keys).any() or set(map(tuple, runs[keys].to_numpy())) != expected:
        raise ValueError("Expected five distinct repetitions of all five stages at each capacity")
    if not runs.status.eq("ok").all():
        raise ValueError("A benchmark stage failed")
    for key, value in (("dataset", "sepsis"), ("case_id", "AG"), ("K", 1),
                       ("trace_capacity", 185), ("trace_length", 5), ("alignment_length", 18)):
        if not runs[key].eq(value).all():
            raise ValueError(f"Controlled input changed: {key}")
    if runs.threads.nunique() != 1 or not runs.gomaxprocs.eq(runs.threads).all():
        raise ValueError("Worker thread counts differ")
    if (runs.groupby("alignment_capacity").constraints.nunique() != 1).any():
        raise ValueError("Constraint count changed across repetitions")
    metrics = runs[["operation_seconds", "worker_seconds", "process_peak_rss_bytes"]].to_numpy()
    if not np.isfinite(metrics).all() or not (metrics > 0).all():
        raise ValueError("Invalid time or memory observation")
    if (runs.worker_seconds < runs.operation_seconds).any():
        raise ValueError("Whole-stage time cannot be shorter than the enclosed operation")
    expected_summary = {(b, s) for b in BOUNDS for s in STAGES}
    if summary.duplicated(keys[:2]).any() or set(map(tuple, summary[keys[:2]].to_numpy())) != expected_summary:
        raise ValueError("Incomplete or duplicate summary")
    if not summary.n_repetitions.eq(5).all() or not summary.complete.eq(True).all():
        raise ValueError("Summary is not complete")
    indexed = summary.set_index(keys[:2])
    for key, group in runs.groupby(keys[:2]):
        row = indexed.loc[key]
        for field, prefix, unit, divisor in (
            ("operation_seconds", "time", "s", 1),
            ("process_peak_rss_bytes", "mem", "mb", 1_000_000),
        ):
            values = group[field] / divisor
            if not np.allclose(
                [row[f"{prefix}_mean_{unit}"], row[f"{prefix}_sd_{unit}"]],
                [values.mean(), values.std(ddof=1)], rtol=1e-9, atol=1e-12,
            ):
                raise ValueError(f"Summary disagrees with raw observations: {key}, {field}")


def elapsed_summary(runs, summary):
    """Keep both timing definitions; never relabel operation-only time as total."""
    result = summary.rename(columns={"time_mean_s": "operation_time_mean_s",
                                     "time_sd_s": "operation_time_sd_s"}).copy()
    worker = runs.groupby(["alignment_capacity", "stage"]).worker_seconds.agg(
        worker_time_mean_s="mean", worker_time_sd_s="std").reset_index()
    result = result.merge(worker, on=["alignment_capacity", "stage"], validate="one_to_one")
    result["plotted_time_metric"] = "worker_seconds"
    result["time_scope"] = "fresh process: startup, loading, operation, output; harness elapsed"
    result["memory_scope"] = "whole-process OS peak RSS"
    return result


@plt.rc_context({"font.serif": ["Times New Roman", "DejaVu Serif"],
                 "font.family": "serif", "mathtext.fontset": "stix",
                 "font.size": 8, "axes.labelsize": 8.5,
                 "xtick.labelsize": 8, "ytick.labelsize": 8,
                 "legend.fontsize": 8, "axes.linewidth": 0.6,
                 "pdf.fonttype": 42})
def draw(frame, path):
    fig, axes = plt.subplots(1, 2, figsize=(12.2 / 2.54, 5.6 / 2.54))
    for phase, label, color, marker, style in SERIES:
        g = frame[frame.stage == phase].sort_values("alignment_capacity")
        for ax, metric, unit in ((axes[0], "worker_time", "s"), (axes[1], "mem", "mb")):
            ax.errorbar(g.alignment_capacity, g[f"{metric}_mean_{unit}"],
                        yerr=g[f"{metric}_sd_{unit}"], color=color, marker=marker,
                        linestyle=style, linewidth=1, markersize=3.2,
                        markerfacecolor="white", markeredgewidth=.8,
                        capsize=2.5, capthick=.8, elinewidth=.8,
                        ecolor=color, alpha=1, label=label)
    for ax in axes:
        ax.set_xticks(BOUNDS)
        ax.set_xlim(18, 398)
        ax.tick_params(axis="both", which="major", length=3, width=.6)
        ax.grid(True, which="major", linestyle="--", linewidth=.4, alpha=.35)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yscale("log")
    axes[0].set_ylim(0.005, 20)
    axes[0].set_ylabel("Time (s)")
    axes[1].set_ylim(-60, 2250)
    axes[1].set_yticks([0, 500, 1000, 1500, 2000])
    axes[1].set_ylabel("Peak memory (MB)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center",
               ncol=2, frameon=False, columnspacing=2, handlelength=2.5)
    fig.supxlabel(r"Alignment capacity $B_\gamma$ (moves)", fontsize=9, y=.035)
    fig.subplots_adjust(left=.12, right=.975, bottom=.21, top=.76, wspace=.52)
    fig.savefig(path)
    plt.close(fig)


def generate(source, data, figures, reports):
    source, data, figures, reports = map(Path, (source, data, figures, reports))
    runs = pd.read_csv(source / "capacity_performance_runs.csv")
    summary = pd.read_csv(source / "capacity_performance_summary.csv")
    validate(runs, summary)
    # Check the recorded measurements themselves, not just the exported summary.
    for row in runs.itertuples():
        measurement = json.loads(Path(row.measurement_file).read_text())
        if measurement["status"] != "ok" or measurement["stage"] != row.stage:
            raise ValueError(f"Failed or mismatched measurement: {row.measurement_file}")
        if not np.isclose(measurement["operation_seconds"], row.operation_seconds, rtol=1e-9, atol=1e-12):
            raise ValueError(f"Measurement time mismatch: {row.measurement_file}")
        if not np.isclose(measurement["worker_seconds"], row.worker_seconds, rtol=1e-9, atol=1e-12):
            raise ValueError(f"Whole-stage time mismatch: {row.measurement_file}")
        if measurement["process_peak_rss_bytes"] != row.process_peak_rss_bytes:
            raise ValueError(f"Measurement memory mismatch: {row.measurement_file}")
    reported = elapsed_summary(runs, summary)
    reported["source_summary"] = str(source / "capacity_performance_summary.csv")
    reported["source_runs"] = str(source / "capacity_performance_runs.csv")
    reported["error_bar"] = "sample_standard_deviation"
    reported["memory_unit"] = "MB (1000000 bytes)"
    frame = reported[reported.stage != "verify"].copy()
    data.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    csv = data / "fig_capacity_performance.csv"
    pdf = figures / "fig_capacity_performance.pdf"
    # Preserve the earlier operation-only figure and data before replacing them.
    if csv.exists() and "worker_time_mean_s" not in pd.read_csv(csv, nrows=0).columns:
        for old in (csv, pdf):
            backup = old.with_stem(old.stem + "_operation_only")
            if old.exists() and not backup.exists():
                shutil.copy2(old, backup)
    reported.to_csv(reports / "capacity_performance_summary.csv", index=False)
    frame.to_csv(csv, index=False)
    draw(pd.read_csv(csv), pdf)
    print("Validated 125 stage measurements; all 25 generated proofs verified.")
    print(f"Figure CSV: {csv}")
    print(f"Figure PDF: {figures / 'fig_capacity_performance.pdf'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=Path("outputs/evaluation/capacity-performance/results"))
    parser.add_argument("--data", type=Path, default=Path("eval/plotting/data"))
    parser.add_argument("--figures", type=Path, default=Path("eval/results/figures"))
    parser.add_argument("--reports", type=Path, default=Path("eval/results"))
    args = parser.parse_args()
    generate(args.source, args.data, args.figures, args.reports)
