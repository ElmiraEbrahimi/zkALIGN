"""Direct plaintext/zkALIGN time comparison from existing paired repeats."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter

from .overhead import validate


def generate(results, data, figures):
    pairs = pd.read_csv(results / "overhead.csv")
    timings = pd.read_csv(results / "repeated_timings.csv")
    summary = pd.read_csv(results / "overhead_summary.csv")
    cases = summary[summary.scope == "case"].copy()
    validate(pairs, timings, cases)
    # Keep AG in the source benchmarks, but show the same three roles per log.
    cases = cases[cases.roles.str.contains(r"short|median|long", regex=True)].copy()
    if cases.groupby("dataset").size().to_dict() != {
        "bpic13cp": 3, "hospital": 3, "rtfm": 3, "sepsis": 3,
    }:
        raise ValueError("Expected short, median and long cases for each log")
    rows = []
    for _, case in cases.iterrows():
        observations = pairs[(pairs.dataset == case.dataset) & (pairs["index"] == case["index"])]
        for method, metric in (("PM4Py", "plaintext_alignment_seconds"),
                               ("zkALIGN", "prover_operation_seconds")):
            rows.append(dict(
                dataset=case.dataset, case_index=int(case["index"]), case_id=case.case_id,
                roles=case.roles, trace_length=int(case.trace_length),
                alignment_length=int(case.alignment_length), K=1, threads="default",
                method=method, time_mean_s=observations[metric].mean(),
                time_sd_s=observations[metric].std(ddof=1), repetitions=len(observations),
                included_operations="alignment" if method == "PM4Py" else "alignment + input-witness encoding + proving",
                excluded_operations="startup, artifact loading, serialization, setup, verification",
                error_bar="sample standard deviation of paired per-repeat times",
                source_pairs=str(results / "overhead.csv"),
                source_timings=str(results / "repeated_timings.csv"),
            ))
    frame = pd.DataFrame(rows)
    if len(frame) != 24 or not frame.repetitions.eq(5).all():
        raise ValueError("Expected two methods for 12 cases, each with five repetitions")
    data.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    csv = data / "fig_plaintext_comparison.csv"
    frame.to_csv(csv, index=False)
    draw(pd.read_csv(csv), figures / "fig_plaintext_comparison.pdf")
    print(f"Validated all 65 paired repeats; plotted 60 repeats across 12 cases. Saved {csv} and comparison PDF.")


def draw(frame, path):
    datasets = [("bpic13cp", "BPI 2013"), ("rtfm", "Road Traffic Fines"),
                ("sepsis", "Sepsis"), ("hospital", "Hospital Billing")]
    def rank(role):
        return 0 if "short" in role else 1 if "median" in role else 3 if "long" in role else 2
    def label(role):
        return "Short" if "short" in role else "Median" if "median" in role else "Long"
    with plt.rc_context({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "mathtext.fontset": "stix", "font.size": 8,
                         "axes.labelsize": 8, "axes.titlesize": 8, "xtick.labelsize": 7,
                         "ytick.labelsize": 7, "legend.fontsize": 8,
                         "axes.linewidth": .6, "pdf.fonttype": 42}):
        fig, ax = plt.subplots(figsize=(12.2/2.54, 5.2/2.54))
        ticks, tick_labels = [], []
        for group_index, (dataset, title) in enumerate(datasets):
            part = frame[frame.dataset == dataset]
            ids = sorted(part.case_index.unique(), key=lambda i: rank(part[part.case_index == i].roles.iloc[0]))
            x = np.arange(len(ids)) + group_index * 4
            for method, offset, color in (("PM4Py", -.19, "#8c2d26"),
                                          ("zkALIGN", .19, "#2171b5")):
                values = part[part.method == method].set_index("case_index").loc[ids]
                ax.bar(x + offset, values.time_mean_s, width=.34, color=color,
                       edgecolor=color, linewidth=.3,
                       label=("Plaintext (PM4Py)" if method == "PM4Py" else "zkALIGN") if group_index == 0 else None,
                       yerr=values.time_sd_s, error_kw={"elinewidth": .7, "capsize": 1.8, "capthick": .7})
            for i, position in zip(ids, x):
                case = part[part.case_index == i].iloc[0]
                ticks.append(position)
                tick_labels.append(f"{label(case.roles)}\n({int(case.alignment_length)})")
            ax.text(x.mean(), -.33, title, ha="center", va="top",
                    transform=ax.get_xaxis_transform(), fontsize=7.5)
        ax.set_xticks(ticks, tick_labels, fontsize=7)
        ax.set_xlim(-.75, 14.75)
        ax.set_yscale("log")
        ax.set_ylim(.0002, 3)
        ax.yaxis.set_major_locator(FixedLocator([.001, .01, .1, 1]))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.tick_params(axis="y", which="minor", length=0)
        ax.grid(axis="y", which="major", linestyle="--", linewidth=.4, alpha=.35)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", length=2, pad=3)
        ax.set_ylabel("Computation time (s, log scale)")
        ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.23), ncol=2,
                  frameon=False, handlelength=1.4, columnspacing=1.5)
        fig.subplots_adjust(left=.115, right=.99, bottom=.30, top=.83)
        fig.savefig(path)
        plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("eval/results"))
    parser.add_argument("--data", type=Path, default=Path("eval/plotting/data"))
    parser.add_argument("--figures", type=Path, default=Path("eval/results/figures"))
    args = parser.parse_args()
    generate(args.results, args.data, args.figures)
