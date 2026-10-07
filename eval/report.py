"""Generate paper artifacts from measured CSVs; never invent missing results."""

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from eval.data import ROOT
from eval.run import csv_write

LABELS = {
    "bpic13cp": "BPI 2013",
    "rtfm": "Traffic",
    "hospital": "Billing",
    "sepsis": "Sepsis",
}
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 8,
        "axes.labelsize": 8,
        "legend.fontsize": 7,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def plot_save(fig, path):
    fig.tight_layout(pad=0.6)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def report(root):
    root = Path(root)
    results = root / "results"
    figures = results / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    notes = [
        "# Evaluation results",
        "",
        "Generated from raw stage measurements. A solver success is not a proof.",
        "Research-only case CSVs can contain costs/IDs; do not include them in a live auditor package.",
        "Memory is RSS in bytes (plots use MiB). OS peaks are per fresh process, including input loading and serialization.",
        "Operation times exclude loading/serialization. Worker times include them. Witness means gnark input encoding; proving includes constraint solving.",
        "Main-cohort timings are functional-run observations; repeated timings are the performance sample.",
        "",
    ]

    def read(name):
        p = results / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

    datasets = read("datasets.csv")
    utility = read("utility_summary.csv")
    cases = read("utility_cases.csv")
    measured = read("measurements.csv")
    repeat = read("repeated_timings.csv")
    repeated_setup = read("repeated_setup.csv")
    if not measured.empty:
        size_rows = []
        for dataset, group in measured.groupby("dataset"):
            row = {"dataset": dataset}
            for phase, field in (
                ("compile", "r1cs"),
                ("setup", "pk"),
                ("setup", "vk"),
                ("prove", "proof"),
                ("prove", "bundle"),
            ):
                if field in group:
                    values = pd.to_numeric(
                        group[group.stage == phase][field], errors="coerce"
                    ).dropna()
                    if len(values):
                        row[field + "_min_bytes"] = int(values.min())
                        row[field + "_max_bytes"] = int(values.max())
            size_rows.append(row)
        csv_write(results / "artifact_sizes.csv", size_rows)
    aggregates = []
    timing = repeat if not repeat.empty else measured
    if not timing.empty:
        if not repeat.empty:
            timing = timing[timing["threads"].astype(str) == "default"]
        for (dataset, stage), group in timing.groupby(["dataset", "stage"]):
            if stage not in (
                "compile",
                "setup",
                "alignment",
                "witness",
                "prove",
                "verify",
            ):
                continue
            for metric in (
                "operation_seconds",
                "worker_seconds",
                "process_peak_rss_bytes",
                "sampled_operation_peak_rss_bytes",
            ):
                vals = pd.to_numeric(group[metric], errors="coerce").dropna()
                if len(vals) == 0:
                    continue
                aggregates.append(
                    {
                        "dataset": dataset,
                        "stage": stage,
                        "metric": metric,
                        "n": len(vals),
                        "mean": vals.mean(),
                        "std": vals.std(ddof=1) if len(vals) > 1 else 0,
                        "median": vals.median(),
                        "p95": vals.quantile(0.95),
                        "min": vals.min(),
                        "max": vals.max(),
                        "source": (
                            "repeated_timings.csv"
                            if not repeat.empty
                            else "measurements.csv"
                        ),
                    }
                )
        csv_write(results / "performance_summary.csv", aggregates)
    if not repeat.empty:
        pairs = []
        default = repeat[repeat["threads"].astype(str) == "default"]
        for (dataset, index, run), group in default.groupby(
            ["dataset", "index", "repeat"]
        ):
            g = group.set_index("stage")
            if not all(
                s in g.index for s in ("alignment", "witness", "prove", "verify")
            ):
                continue
            plain = float(g.loc["alignment", "operation_seconds"])
            total = (
                plain
                + float(g.loc["witness", "operation_seconds"])
                + float(g.loc["prove", "operation_seconds"])
            )
            cold = sum(
                float(g.loc[s, "worker_seconds"])
                for s in ("alignment", "witness", "prove")
            )
            pairs.append(
                {
                    "dataset": dataset,
                    "index": index,
                    "repeat": run,
                    "plaintext_alignment_seconds": plain,
                    "prover_operation_seconds": total,
                    "operation_overhead": total / plain if plain else None,
                    "fresh_worker_seconds": cold,
                    "verifier_seconds": float(g.loc["verify", "operation_seconds"]),
                }
            )
        csv_write(results / "overhead.csv", pairs)
        if pairs:
            grouped = pd.DataFrame(pairs).groupby("dataset").mean(numeric_only=True)
            names = list(grouped.index)
            fig, ax = plt.subplots(figsize=(4.8, 1.9))
            for offset, column, label, hatch in (
                (-0.18, "plaintext_alignment_seconds", "Plaintext alignment", ""),
                (0.18, "prover_operation_seconds", "Alignment + witness + proof", "//"),
            ):
                ax.bar(
                    np.arange(len(names)) + offset,
                    grouped[column],
                    0.35,
                    label=label,
                    color="white",
                    edgecolor="black",
                    hatch=hatch,
                )
            ax.set_xticks(np.arange(len(names)), [LABELS[n] for n in names])
            ax.set_ylabel("Operation time (s)")
            ax.set_yscale("log")
            ax.legend(
                fontsize=7,
                loc="upper center",
                bbox_to_anchor=(0.5, 1.25),
                ncol=2,
                frameon=False,
            )
            plot_save(fig, figures / "fig_overhead.pdf")
    if not utility.empty:
        u = utility[
            (utility["mode"] == "groth16")
            & (utility["K"] == 1)
            & (utility["processed"] == utility["N"])
        ]
        if len(u):
            x = np.arange(len(u))
            fig, ax = plt.subplots(figsize=(4.8, 1.85))
            ax.bar(
                x - 0.18,
                u.reference_share * 100,
                0.36,
                label="Plaintext",
                color="white",
                edgecolor="black",
            )
            ax.bar(
                x + 0.18,
                u.certified_share * 100,
                0.36,
                label="Certified",
                color=".6",
                edgecolor="black",
                hatch="//",
            )
            ax.set_xticks(x, [LABELS.get(v, v) for v in u.dataset])
            ax.set_ylabel("Cases (%)")
            ax.set_ylim(0, 115)
            ax.legend(loc="upper center", ncol=2, frameon=False)
            plot_save(fig, figures / "fig_utility.pdf")
        for _, r in utility.iterrows():
            notes.append(
                f"- {r.dataset}, K={r.K}, {r['mode']}: processed {r.processed}/{r.N}, reference-qualified {r.reference_qualified}, certified {r.certified}, errors {r.errors}. Source: utility_summary.csv."
            )
    if aggregates:
        a = pd.DataFrame(aggregates)
        names = sorted(a.dataset.unique())
        fig, axes = plt.subplots(1, 2, figsize=(4.8, 2.0))
        for ax, metric, unit in zip(
            axes,
            ["operation_seconds", "process_peak_rss_bytes"],
            ["Time (s)", "Peak RSS (MiB)"],
        ):
            for offset, phase, hatch in [
                (-0.24, "witness", ""),
                (0, "prove", "//"),
                (0.24, "verify", "xx"),
            ]:
                rows = a[(a.metric == metric) & (a.stage == phase)].set_index("dataset")
                vals = [
                    rows.loc[n, "mean"] if n in rows.index else np.nan for n in names
                ]
                if metric.endswith("bytes"):
                    vals = np.array(vals) / 1024**2
                ax.bar(
                    np.arange(len(names)) + offset,
                    vals,
                    0.23,
                    color="white",
                    edgecolor="black",
                    hatch=hatch,
                    label=phase,
                )
            ax.set_xticks(
                np.arange(len(names)), [LABELS.get(n, n) for n in names], rotation=20
            )
            ax.set_yscale("log")
            ax.set_ylabel(unit)
        axes[0].legend(
            fontsize=6,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.25),
            ncol=3,
            frameon=False,
        )
        plot_save(fig, figures / "fig_time_memory.pdf")
    setup = (
        measured[measured.stage.isin(["compile", "setup"])]
        if not measured.empty
        else pd.DataFrame()
    )
    if not repeated_setup.empty:
        setup = repeated_setup
        setup_rows = []
        for (dataset, phase), group in setup.groupby(["dataset", "stage"]):
            for metric in (
                "operation_seconds",
                "worker_seconds",
                "process_peak_rss_bytes",
            ):
                v = group[metric]
                setup_rows.append(
                    {
                        "dataset": dataset,
                        "stage": phase,
                        "metric": metric,
                        "n": len(v),
                        "mean": v.mean(),
                        "std": v.std(),
                        "median": v.median(),
                        "max": v.max(),
                    }
                )
        csv_write(results / "setup_summary.csv", setup_rows)
    if not setup.empty:
        names = sorted(setup.dataset.unique())
        fig, axes = plt.subplots(1, 2, figsize=(4.8, 1.9))
        for ax, metric, unit in zip(
            axes,
            ["operation_seconds", "process_peak_rss_bytes"],
            ["Time (s)", "Peak RSS (MiB)"],
        ):
            for offset, phase, hatch in [(-0.18, "compile", ""), (0.18, "setup", "//")]:
                g = setup[setup.stage == phase].groupby("dataset")[metric].mean()
                values = [g.get(n, np.nan) for n in names]
                if metric.endswith("bytes"):
                    values = np.array(values) / 1024**2
                ax.bar(
                    np.arange(len(names)) + offset,
                    values,
                    0.35,
                    label=phase,
                    color="white",
                    edgecolor="black",
                    hatch=hatch,
                )
            ax.set_xticks(
                np.arange(len(names)), [LABELS.get(n, n) for n in names], rotation=20
            )
            ax.set_ylabel(unit)
            ax.set_yscale("log")
        axes[0].legend(
            fontsize=6,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.25),
            ncol=2,
            frameon=False,
        )
        plot_save(fig, figures / "fig_setup_time_memory.pdf")
    scale = read("scal_model.csv")
    if not scale.empty:
        fig, axes = plt.subplots(1, 2, figsize=(4.8, 1.9))
        for (family, group), marker in zip(
            scale[scale.stage == "prove"].groupby("family"), ["o", "s", "^", "x"]
        ):
            g = group.groupby("activities").mean(numeric_only=True)
            axes[0].plot(
                g.index, g.constraints, "-" + marker, color="black", label=family
            )
            axes[1].plot(
                g.index, g.operation_seconds, "-" + marker, color="black", label=family
            )
        axes[0].set_ylabel("Constraints")
        axes[1].set_ylabel("Proving time (s)")
        for ax in axes:
            ax.set_xlabel("Visible activities")
        axes[1].legend(fontsize=6)
        plot_save(fig, figures / "fig_model_scalability.pdf")
    capacity = read("scal_capacity.csv")
    if not capacity.empty:
        g = (
            capacity[capacity.stage == "prove"]
            .groupby("alignment_capacity")
            .mean(numeric_only=True)
        )
        fig, axes = plt.subplots(1, 2, figsize=(4.8, 1.9))
        axes[0].plot(g.index, g.constraints, "o-", color="black")
        axes[0].set_ylabel("Constraints")
        axes[1].plot(g.index, 100 * g.fit / g.N, "s-", color="black")
        axes[1].set_ylabel("Cases fitting (%)")
        for ax in axes:
            ax.set_xlabel("Alignment capacity")
        plot_save(fig, figures / "fig_capacity.pdf")
    if not cases.empty:
        s = cases[
            (cases.dataset == "sepsis")
            & (cases["mode"] == "groth16")
            & (cases.reason == "certified")
        ]
        if len(s):
            fig, ax = plt.subplots(figsize=(4.8, 1.8))
            ax.scatter(
                s.trace_length,
                s.prove_seconds,
                s=9,
                facecolors="none",
                edgecolors="black",
                linewidths=0.5,
            )
            ax.set_xlabel("Actual trace length")
            ax.set_ylabel("Proving time (s)")
            plot_save(fig, figures / "fig_trace_length.pdf")
            s.to_csv(results / "scal_length.csv", index=False)
    population = read("scal_population.csv")
    if not population.empty:
        g = population.groupby("N").mean(numeric_only=True)
        fig, ax = plt.subplots(figsize=(4.8, 1.8))
        ax.loglog(g.index, g.operation_seconds, "o-", color="black")
        ax.set_xlabel("Synthetic roster entries")
        ax.set_ylabel("Root validation time (s)")
        plot_save(fig, figures / "fig_population.pdf")
    integrity = read("integrity.csv")
    if not integrity.empty:
        notes.append(
            f"- Integrity attempts {int(integrity.attempts.sum())}, unexpected outcomes {int(integrity.unexpected.sum())}, inapplicable mutations {int(integrity.skipped.sum())}. Source: integrity.csv."
        )
    proof_pop = read("scal_population_proofs.csv")
    if not proof_pop.empty:
        for _, r in proof_pop.iterrows():
            notes.append(
                f"- Distinct-certificate audit N={int(r.N)}: {int(r.certified)} certified, "
                f"{r.operation_seconds:.6f} s audit operation. Source: scal_population_proofs.csv."
            )
    if not measured.empty:
        for _, r in measured[measured.stage.isin(["compile", "setup"])].iterrows():
            notes.append(
                f"- {r.dataset} {r.stage}: operation {r.operation_seconds:.6f} s, process RSS {r.process_peak_rss_bytes/1024**2:.2f} MiB. Source: measurements.csv, measurement={r.measurement}."
            )
    expected = [
        "datasets.csv",
        "utility_cases.csv",
        "utility_summary.csv",
        "measurements.csv",
        "repeated_timings.csv",
        "repeated_setup.csv",
        "integrity.csv",
        "scal_model.csv",
        "scal_capacity.csv",
        "scal_population.csv",
        "scal_population_proofs.csv",
    ]
    missing = [p for p in expected if not (results / p).exists()]
    notes.extend(
        [
            "",
            "## Completeness",
            "Missing experiment files: " + (", ".join(missing) if missing else "none"),
        ]
    )
    if not utility.empty and any(utility.processed != utility.N):
        notes.append(
            "At least one cohort run is incomplete. Do not present it as a complete utility result."
        )
    (results / "README.md").write_text("\n".join(notes) + "\n")
    tex = [
        r"% Generated measurements, not a standalone manuscript.",
        r"\subsection{Experimental Setup and Datasets}",
        r"We evaluate individual trace certificates on four public event logs. Cases are split before discovery and audit populations are fixed before alignment computation. Each evaluation population has its own complete commitment root. Model and capacity configurations are compiled separately.",
        r"\subsection{Utility Preservation and Certification Coverage}",
        r"The plaintext reference uses zero cost for synchronous and silent model moves and unit cost for log and visible model moves. At $K=1$, certification is measured using actual Groth16 proofs and the auditor's population counter. Results at other thresholds must be identified as solver checks unless real proofs were generated.",
    ]
    if not utility.empty:
        for _, r in utility[
            (utility["mode"] == "groth16")
            & (utility.K == 1)
            & (utility.processed == utility.N)
        ].iterrows():
            tex.append(
                f"For {LABELS.get(r.dataset,r.dataset)}, {int(r.certified)} of {int(r.N)} cases were certified, compared with {int(r.reference_qualified)} qualifying cases in the plaintext reference."
            )
    tex += [
        r"\subsection{Circuit and Audit Integrity}",
        r"We distinguish deliberately invalid evidence from legitimate alternative executions. Duplicate submissions must leave the certified count unchanged, and rejected submissions must not prevent a subsequent valid certificate.",
        r"\subsection{Performance Evaluation}",
        r"Compilation, setup, witness encoding, proving, and verification run in separate operating-system processes. We report per-process peak resident memory and operation wall time separately from complete worker time. Memory sampling uses a nominal interval of 5 milliseconds. Sub-interval stages may have no operation sample, in which case only their process peak is reported. In gnark, witness encoding does not solve the constraints. Proving includes constraint solving.",
        r"\subsection{Scalability Analysis}",
        r"We vary alignment capacity while holding the Sepsis model fixed, and vary the size of controlled sequence, choice, parallel, and loop models at fixed trace and alignment capacities. Root reconstruction for large synthetic rosters is measured separately from verification of distinct real certificates.",
    ]
    (results / "evaluation_results.tex").write_text("\n\n".join(tex) + "\n")
    tables = [
        r"% Requires booktabs. Tables summarize complete measured runs only.",
        r"\begin{table}[t]\centering\small",
        r"\caption{Evaluation models and frozen audit populations.}",
        r"\begin{tabular}{lrrrrrr}\toprule",
        r"Log & Cases & Activities & Places & Transitions & $B_\gamma$ & Constraints\\\midrule",
    ]
    if not datasets.empty:
        for _, r in datasets.iterrows():
            tables.append(
                f"{LABELS.get(r.dataset, r.dataset)} & {int(r.population)} & "
                f"{int(r.activities)} & {int(r.places)} & {int(r.transitions)} & "
                f"{int(r.alignment_capacity)} & {int(r.constraints)}" + r"\\"
            )
    tables += [r"\bottomrule\end{tabular}\end{table}"]
    (results / "evaluation_tables.tex").write_text("\n".join(tables) + "\n")
    return figures


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    print(report(p.parse_args().root))
