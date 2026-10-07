"""One self-contained source CSV per figure; reproduce with --from-csv."""

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

BLUE, RED, GREEN, PURPLE = "#0000FF", "#FF0000", "#008000", "#800080"
LABELS = {
    "bpic13cp": "BPI 2013",
    "rtfm": "Traffic",
    "hospital": "Billing",
    "sepsis": "Sepsis",
}
STYLE = {
    "sequence": (BLUE, "o"),
    "choice": (RED, "s"),
    "parallel": (GREEN, "^"),
    "loop": (PURPLE, "D"),
}
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "legend.fontsize": 7,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def finish(fig, path, height=4.5, top=0.96):
    fig.set_size_inches(12.2 / 2.54, height / 2.54)
    for ax in fig.axes:
        ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.45)
        ax.set_axisbelow(True)
    fig.tight_layout(pad=0.7, rect=(0, 0, 1, top))
    fig.savefig(path)
    plt.close(fig)


def utility(frame, path):
    names = [n for n in LABELS if n in set(frame.dataset)]
    fig, axes = plt.subplots(1, len(names), squeeze=False, sharey=True)
    for ax, name in zip(axes[0], names):
        g = frame[frame.dataset == name].sort_values("K")
        ax.plot(g.K, g.zk_share * 100, color=BLUE, linewidth=0.8)
        for mode, marker, face in (("groth16", "s", BLUE), ("solver", "o", "white")):
            rows = g[g["mode"] == mode]
            ax.scatter(
                rows.K,
                rows.zk_share * 100,
                marker=marker,
                s=35,
                facecolor=face,
                edgecolor=BLUE,
                zorder=3,
            )
        ax.plot(
            g.K,
            g.reference_share * 100,
            "x--",
            color=RED,
            markersize=4,
            linewidth=0.7,
            zorder=4,
        )
        ax.set_title(LABELS[name])
        ax.set_xlabel("Threshold K")
        ax.set_xticks([0, 1, 2, 3])
        ax.set_ylim(
            max(
                0,
                5
                * np.floor(
                    100 * min(frame.reference_share.min(), frame.zk_share.min()) / 5
                )
                - 5,
            ),
            103,
        )
    axes[0, 0].set_ylabel("Cases (%)")
    handles = [
        Line2D([], [], color=RED, marker="x", linestyle="--", label="Plaintext"),
        Line2D([], [], color=BLUE, marker="s", linestyle="none", label="Groth16 (K=1)"),
        Line2D(
            [],
            [],
            color=BLUE,
            marker="o",
            markerfacecolor="white",
            linestyle="none",
            label="Solver (K=0,2,3)",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        ncol=3,
        frameon=False,
        handlelength=1.2,
        columnspacing=1,
    )
    finish(fig, path, height=4.8, top=0.84)


def overhead(frame, path):
    names = [n for n in LABELS if n in set(frame.dataset)]
    fig, axes = plt.subplots(1, len(names), squeeze=False, sharey=True)
    for ax, name in zip(axes[0], names):
        g = frame[frame.dataset == name].sort_values(["alignment_length", "index"])
        x = np.arange(len(g))
        ax.errorbar(
            x,
            g.operation_overhead_mean,
            yerr=g.operation_overhead_sd,
            fmt="o",
            color=BLUE,
            capsize=2,
            markersize=3,
        )
        ax.axhline(
            g.dataset_median_case_overhead.iloc[0],
            color=RED,
            linestyle="--",
            linewidth=0.8,
        )
        labels = [
            s.replace("median", "mid").replace("long+NGA", "long/NGA") for s in g.roles
        ]
        ax.set_xticks(x, labels, rotation=55, ha="right")
        ax.set_title(LABELS[name])
        ax.set_yscale("log")
        ax.set_xlim(-0.5, len(g) - 0.5)
    axes[0, 0].set_ylabel("Prover / plaintext time")
    fig.legend(
        handles=[
            Line2D(
                [],
                [],
                color=BLUE,
                marker="o",
                linestyle="none",
                label="Case mean +/- SD (5 repeats)",
            ),
            Line2D([], [], color=RED, linestyle="--", label="Median of case means"),
        ],
        loc="upper center",
        ncol=2,
        frameon=False,
        handlelength=1.3,
        columnspacing=1,
    )
    finish(fig, path, height=5.6, top=0.86)


def stage_plot(frame, path, stages):
    fig, axes = plt.subplots(1, 2)
    names = [n for n in LABELS if n in set(frame.dataset)]
    colors = [BLUE, RED, GREEN]
    for ax, metric, divisor, label in zip(
        axes,
        ("operation_seconds", "process_peak_rss_bytes"),
        (1, 1024**2),
        ("Operation time (s)", "Process peak RSS (MiB)"),
    ):
        for i, phase in enumerate(stages):
            g = (
                frame[(frame.stage == phase) & (frame.metric == metric)]
                .set_index("dataset")
                .reindex(names)
            )
            ax.errorbar(
                np.arange(len(names)) + (i - (len(stages) - 1) / 2) * 0.17,
                g["mean"] / divisor,
                yerr=g["std"] / divisor,
                color=colors[i],
                fmt=["o", "s", "^"][i],
                capsize=2,
                markersize=3,
                label=phase,
            )
        ax.set_xticks(range(len(names)), [LABELS[n] for n in names], rotation=20)
        ax.set_yscale("log")
        ax.set_ylabel(label)
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        loc="upper center",
        ncol=len(stages),
        frameon=False,
    )
    finish(fig, path, height=4.8, top=0.85)


def models(frame, path):
    fig, axes = plt.subplots(1, 2)
    for family, (color, marker) in STYLE.items():
        g = frame[frame.family == family].sort_values("activities")
        axes[0].plot(
            g.activities,
            g.constraints / 1000,
            color=color,
            marker=marker,
            markersize=3,
            linewidth=0.9,
            label=family,
        )
        axes[1].errorbar(
            g.activities,
            g.prove_seconds_mean,
            yerr=g.prove_seconds_sd,
            color=color,
            marker=marker,
            markersize=3,
            linewidth=0.9,
            capsize=2,
            label=family,
        )
    axes[0].set_ylabel("Constraints (thousands)")
    axes[1].set_ylabel("Proving time (s)")
    for ax in axes:
        ax.set_xlabel("Visible activities")
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        loc="upper center",
        ncol=4,
        frameon=False,
        columnspacing=0.9,
        handlelength=1.4,
    )
    finish(fig, path, height=4.8, top=0.85)


def capacity(frame, path):
    fig, axes = plt.subplots(1, 2)
    axes[0].plot(
        frame.alignment_capacity,
        frame.constraints / 1000,
        "o-",
        color=BLUE,
        markersize=3,
    )
    axes[0].set_ylabel("Constraints (thousands)")
    axes[1].plot(
        frame.alignment_capacity, frame.coverage_pct, "s-", color=RED, markersize=3
    )
    axes[1].set_ylabel("Cases fitting (%)")
    for ax in axes:
        ax.set_xlabel("Alignment capacity")
    finish(fig, path)


def trace_length(frame, path):
    fig, ax = plt.subplots()
    functional = frame[frame.measurement_kind == "functional_single_run"]
    ax.scatter(
        functional.trace_length,
        functional.prove_seconds,
        s=12,
        facecolors="none",
        edgecolors=BLUE,
        alpha=0.45,
        linewidths=0.6,
        label="Functional run (one per case)",
    )
    repeated = frame[frame.measurement_kind == "repeated_selected_case"]
    if len(repeated):
        ax.errorbar(
            repeated.trace_length,
            repeated.prove_seconds,
            yerr=[
                repeated.prove_seconds - repeated.prove_seconds_min,
                repeated.prove_seconds_max - repeated.prove_seconds,
            ],
            fmt="s",
            color=RED,
            markersize=3,
            capsize=3,
            label="Selected cases: median, min-max (5 runs)",
        )
    ax.set_xlabel("Actual trace length")
    ax.set_ylabel("Proving time (s)")
    ax.legend(loc="upper right", frameon=False, fontsize=6.5)
    finish(fig, path)


def population(frame, path):
    fig, ax = plt.subplots()
    ax.errorbar(
        frame.N,
        frame["mean"],
        yerr=frame["std"],
        fmt="o-",
        color=BLUE,
        capsize=3,
        markersize=4,
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Synthetic roster entries")
    ax.set_ylabel("Root validation time (s)")
    finish(fig, path)


DRAW = {
    "fig_utility": utility,
    "fig_overhead": overhead,
    "fig_model_scalability": models,
    "fig_capacity": capacity,
    "fig_trace_length": trace_length,
    "fig_population": population,
    "fig_time_memory": lambda f, p: stage_plot(f, p, ["witness", "prove", "verify"]),
    "fig_setup_time_memory": lambda f, p: stage_plot(f, p, ["compile", "setup"]),
}


def draw_csv(data, figures):
    figures = Path(figures)
    figures.mkdir(parents=True, exist_ok=True)
    for name, draw in DRAW.items():
        source = Path(data) / (name + ".csv")
        if source.exists():
            draw(pd.read_csv(source), figures / (name + ".pdf"))


def generate_figures(results, plotting, figures):
    results, data = Path(results), Path(plotting) / "data"
    data.mkdir(parents=True, exist_ok=True)

    def read(name):
        p = results / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

    def export(name, frame):
        if not frame.empty:
            frame.to_csv(data / (name + ".csv"), index=False)
            DRAW[name](
                pd.read_csv(data / (name + ".csv")), Path(figures) / (name + ".pdf")
            )

    u = read("utility_summary.csv")
    if not u.empty:
        u = u[(u.processed == u.N) & (u.errors == 0)].copy()
        if len(u):
            u["zk_share"] = u.certified_share
            solver = u["mode"] == "solver"
            u.loc[solver, "zk_share"] = (
                u.loc[solver, "solver_satisfied"] / u.loc[solver, "N"]
            )
            u["zk_result_kind"] = np.where(
                solver, "solver_satisfied_not_certified", "verified_certificate"
            )
            export("fig_utility", u)
    overhead_data = read("overhead_summary.csv")
    if not overhead_data.empty:
        export("fig_overhead", overhead_data[overhead_data.scope == "case"])
    for fig, source in (
        ("fig_model_scalability", "scal_model_summary.csv"),
        ("fig_time_memory", "performance_summary.csv"),
        ("fig_setup_time_memory", "setup_summary.csv"),
    ):
        export(fig, read(source))
    c = read("scal_capacity.csv")
    if not c.empty:
        c = (
            c[c.stage == "prove"]
            .groupby("alignment_capacity")
            .agg(
                constraints=("constraints", "first"),
                fit=("fit", "first"),
                N=("N", "first"),
                prove_seconds_mean=("operation_seconds", "mean"),
                prove_seconds_sd=("operation_seconds", "std"),
                n=("operation_seconds", "size"),
            )
            .reset_index()
        )
        c["coverage_pct"] = 100 * c.fit / c.N
        export("fig_capacity", c)
    f, r = read("scal_length.csv"), read("scal_length_repeated.csv")
    if not f.empty:
        columns = [
            "dataset",
            "index",
            "case_id",
            "trace_length",
            "alignment_length",
            "measurement_kind",
            "n",
            "prove_seconds",
        ]
        f = f[columns]
        if not r.empty:
            r = r.rename(columns={"prove_seconds_median": "prove_seconds"})
            f = pd.concat(
                [f, r[columns + ["prove_seconds_min", "prove_seconds_max"]]],
                ignore_index=True,
            )
        export("fig_trace_length", f)
    p = read("scal_population.csv")
    if not p.empty:
        p = (
            p.groupby("N")
            .operation_seconds.agg(["mean", "std", "size"])
            .reset_index()
            .rename(columns={"size": "n"})
        )
        p["measurement_kind"] = "synthetic_root_validation_not_proof_verification"
        export("fig_population", p)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-csv", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument(
        "--figures", type=Path, default=Path(__file__).parents[1] / "results/figures"
    )
    args = parser.parse_args()
    draw_csv(args.from_csv, args.figures)
