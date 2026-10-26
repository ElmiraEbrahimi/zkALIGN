"""Separate capacity plot using operation-only time and whole-process peak RSS.

Reads saved repetitions only. Does not change the existing capacity plotting
script, source data, or figures. Isolated operation memory is not available.
Run: .venv/bin/python -m eval.plotting.capacity_operation
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .capacity_performance import BOUNDS, SERIES, validate


ROOT = Path(__file__).resolve().parents[2]
STEM = "caise_capacity_operation_time"


def load_data(source):
    source = Path(source)
    runs = pd.read_csv(source / "capacity_performance_runs.csv")
    summary = pd.read_csv(source / "capacity_performance_summary.csv")
    validate(runs, summary)
    for row in runs.itertuples():
        record = json.loads(Path(row.measurement_file).read_text())
        if record["status"] != "ok" or record["stage"] != row.stage:
            raise ValueError(f"Invalid measurement: {row.measurement_file}")
        if not np.isclose(record["operation_seconds"], row.operation_seconds,
                          rtol=1e-9, atol=1e-12):
            raise ValueError(f"Operation time mismatch: {row.measurement_file}")
        if record["process_peak_rss_bytes"] != row.process_peak_rss_bytes:
            raise ValueError(f"Memory mismatch: {row.measurement_file}")
    # Calculate both panels and their sample SDs from the original repetitions.
    selected = runs[runs.stage.isin([stage for stage, *_ in SERIES])].copy()
    selected["memory_mb"] = selected.process_peak_rss_bytes / 1_000_000
    keys = ["dataset", "case_id", "K", "trace_capacity", "alignment_capacity",
            "constraints", "threads", "trace_length", "alignment_length", "stage"]
    frame = selected.groupby(keys, as_index=False).agg(
        operation_time_mean_s=("operation_seconds", "mean"),
        operation_time_sd_s=("operation_seconds", "std"),
        mem_mean_mb=("memory_mb", "mean"),
        mem_sd_mb=("memory_mb", "std"),
        repetitions=("repeat", "size"),
    )
    frame["plotted_time_metric"] = "operation_seconds"
    frame["time_scope"] = "internally timed operation; excludes startup, artifact loading, serialization"
    frame["memory_scope"] = "whole-process OS peak RSS; includes runtime and loaded inputs"
    frame["memory_unit"] = "MB (1000000 bytes)"
    frame["error_bar"] = "sample standard deviation"
    frame["source_runs"] = str(source / "capacity_performance_runs.csv")
    return frame


PLOT_STYLE = {
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "mathtext.fontset": "stix", "font.size": 8, "axes.labelsize": 8.5,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "axes.linewidth": 0.6, "pdf.fonttype": 42,
}


@plt.rc_context(PLOT_STYLE)
def make_figure(frame):
    height_cm = 4.5
    fig, axes = plt.subplots(1, 2, figsize=(12.2 / 2.54, height_cm / 2.54))
    for stage, label, color, marker, style in SERIES:
        group = frame[frame.stage == stage].sort_values("alignment_capacity")
        for ax, metric, unit in ((axes[0], "operation_time", "s"),
                                 (axes[1], "mem", "mb")):
            ax.errorbar(
                group.alignment_capacity, group[f"{metric}_mean_{unit}"],
                yerr=group[f"{metric}_sd_{unit}"],
                color=color, marker=marker, linestyle=style, linewidth=1,
                markersize=3.2, markerfacecolor="white", markeredgewidth=.8,
                capsize=2.5, capthick=.8, elinewidth=.8, ecolor=color,
                label=label,
            )
    for ax, panel in zip(axes, ("(a)", "(b)")):
        ax.text(.04, 1.02, panel, transform=ax.transAxes,
                ha="left", va="bottom", fontsize=9, clip_on=False)
        ax.set_xticks(BOUNDS)
        # Keep the two close capacity labels distinct at the compact width.
        ax.get_xticklabels()[0].set_horizontalalignment("right")
        ax.get_xticklabels()[1].set_horizontalalignment("left")
        ax.set_xlim(18, 398)
        ax.tick_params(axis="both", which="major", length=3, width=.6)
        ax.grid(True, which="major", linestyle="--", linewidth=.4, alpha=.35)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yscale("log")
    axes[0].set_ylim(0.00007, 20)
    axes[0].set_yticks([0.0001, 0.001, 0.01, 0.1, 1, 10])
    axes[0].set_ylabel("Time (s)")
    axes[1].set_ylim(-60, 2250)
    axes[1].set_yticks([0, 500, 1000, 1500, 2000])
    axes[1].set_ylabel("Memory (MB)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center",
               ncol=2, frameon=False, columnspacing=2, handlelength=2.5)
    fig.supxlabel(r"Alignment capacity $B_\gamma$ (moves)", fontsize=9,
                  y=.035 * 5.6 / height_cm)
    fig.subplots_adjust(left=.12, right=.975, bottom=.21 * 5.6 / height_cm,
                        top=1 - .27 * 5.6 / height_cm, wspace=.52)
    return fig, axes


@plt.rc_context(PLOT_STYLE)
def generate(source, data, figures):
    frame = load_data(source)
    data, figures = Path(data), Path(figures)
    data.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    csv_path = data / f"{STEM}.csv"
    pdf_path = figures / f"{STEM}.pdf"
    frame.to_csv(csv_path, index=False)
    fig, _ = make_figure(pd.read_csv(csv_path))
    fig.savefig(pdf_path)
    plt.close(fig)
    return csv_path, pdf_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=ROOT / "outputs/evaluation/capacity-performance/results")
    parser.add_argument("--data", type=Path, default=ROOT / "eval/plotting/data")
    parser.add_argument("--figures", type=Path, default=ROOT / "eval/results/figures")
    args = parser.parse_args()
    for path in generate(args.source, args.data, args.figures):
        print(path)


if __name__ == "__main__":
    main()
