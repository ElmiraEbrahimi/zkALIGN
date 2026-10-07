"""Generate paper artifacts from measured CSVs; never invent missing results."""

import argparse
from pathlib import Path
import pandas as pd
from eval.data import ROOT
from eval.run import csv_write
from eval.summaries import (
    enrich_utility,
    overhead_summary,
    model_summary,
    trace_summary,
)
from eval.plotting.draw import generate_figures

LABELS = {
    "bpic13cp": "BPI 2013",
    "rtfm": "Traffic",
    "hospital": "Billing",
    "sepsis": "Sepsis",
}


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
    if not cases.empty and not utility.empty:
        utility = enrich_utility(utility, cases)
        utility.to_csv(results / "utility_summary.csv", index=False)
    if not cases.empty:
        cases[(cases["mode"] == "groth16") & ~cases.certified.astype(bool)].to_csv(
            results / "uncertified_cases.csv", index=False
        )
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
        thread_rows = []
        for (dataset, threads, phase), group in repeat.groupby(
            ["dataset", "threads", "stage"]
        ):
            thread_rows.append(
                {
                    "dataset": dataset,
                    "threads": threads,
                    "stage": phase,
                    "samples": len(group),
                    "mean_operation_seconds": group.operation_seconds.mean(),
                    "std_operation_seconds": group.operation_seconds.std(),
                    "mean_process_peak_rss_bytes": group.process_peak_rss_bytes.mean(),
                    "max_process_peak_rss_bytes": group.process_peak_rss_bytes.max(),
                }
            )
        csv_write(results / "thread_scaling.csv", thread_rows)
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
        if pairs and not cases.empty:
            overhead_summary(pd.DataFrame(pairs), cases).to_csv(
                results / "overhead_summary.csv", index=False
            )
    if not utility.empty:
        for _, r in utility.iterrows():
            notes.append(
                f"- {r.dataset}, K={r.K}, {r['mode']}: processed {r.processed}/{r.N}, reference-qualified {r.reference_qualified}, "
                + (
                    f"certified {r.certified}"
                    if r["mode"] == "groth16"
                    else f"solver-satisfied {r.get('solver_satisfied', 'unavailable')}, solver-rejected {r.get('solver_rejected', 'unavailable')}"
                )
                + f", agreement {r.get('agreement_pct', 'unavailable')}%, errors {r.errors}. Source: utility_summary.csv."
            )
    if aggregates:
        notes += ["", "## Repeated performance samples"]
        for row in aggregates:
            if row["metric"] in ("operation_seconds", "process_peak_rss_bytes"):
                notes.append(
                    f"- {row['dataset']} {row['stage']} {row['metric']}: "
                    f"mean {row['mean']:.9g}, SD {row['std']:.9g}, n={row['n']}. "
                    f"Source: performance_summary.csv / {row['source']}."
                )
    if not repeated_setup.empty:
        setup_rows = []
        for (dataset, phase), group in repeated_setup.groupby(["dataset", "stage"]):
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
    scale = read("scal_model.csv")
    if not scale.empty:
        model_summary(scale).to_csv(results / "scal_model_summary.csv", index=False)
    if not cases.empty:
        functional = cases[
            (cases.dataset == "sepsis")
            & (cases["mode"] == "groth16")
            & (cases.reason == "certified")
        ].copy()
        functional["measurement_kind"] = "functional_single_run"
        functional["n"] = 1
        functional.to_csv(results / "scal_length.csv", index=False)
        if not repeat.empty:
            trace_summary(repeat, cases).to_csv(
                results / "scal_length_repeated.csv", index=False
            )
    generate_figures(results, root / "plotting", figures)
    integrity = read("integrity.csv")
    if not integrity.empty:
        notes.append(
            f"- Integrity attempts {int(integrity.attempts.sum())}, unexpected outcomes {int(integrity.unexpected.sum())}, inapplicable mutations {int(integrity.skipped.sum())}. Source: integrity.csv."
        )
        negatives = integrity[integrity.expected == "reject"]
        notes.append(
            f"- Negative integrity attempts {int(negatives.attempts.sum())}, "
            f"unexpected outcomes {int(negatives.unexpected.sum())}. Valid controls and "
            "duplicate-count invariants are reported separately in integrity.csv."
        )
    proof_pop = read("scal_population_proofs.csv")
    if not proof_pop.empty:
        for _, r in proof_pop.iterrows():
            notes.append(
                f"- Distinct-certificate audit N={int(r.N)}: {int(r.certified)} certified, "
                f"{r.operation_seconds:.6f} s audit operation. Source: scal_population_proofs.csv."
            )
    setup_stats = read("setup_summary.csv")
    notes += ["", "## Repeated compilation and setup"]
    if not setup_stats.empty:
        for _, r in setup_stats[setup_stats.metric == "operation_seconds"].iterrows():
            notes.append(
                f"- {r.dataset} {r.stage}: {r['mean']:.2f} s (SD {r['std']:.2f}), n={int(r.n)}. Source: setup_summary.csv / repeated_setup.csv."
            )
    else:
        notes.append(
            "Repeated setup measurements unavailable. Initial functional runs are not substituted."
        )
    notes += [
        "",
        "## Interpretation",
        "overhead_summary.csv separates each selected case from the pooled selected sample. It is not a population-wide estimate.",
        "Prover operation time = alignment + witness encoding + proving. Overhead is that sum divided by alignment time for each paired repetition; setup, loading and verification are excluded.",
        "dataset_median_case_overhead is the median of the selected cases' mean paired overhead ratios. operation_overhead_median is the median of individual paired ratios.",
        "Error bars denote sample standard deviation (not confidence intervals). Model scaling has three repeats; per-case overhead has five.",
        "scal_model_summary.csv reports places, transitions and arcs as well as constraints. Larger parallel nets are associated with higher circuit cost; these measurements do not isolate a single causal factor.",
        "scal_length.csv contains functional-run observations. scal_length_repeated.csv contains medians and ranges for only the selected repeated Sepsis cases.",
        "Each figure has its own source CSV under plotting/data. Plotting and reporting never start benchmark workers.",
        "A population of 300 included 299 accepted certificates, not 300. Large synthetic roster timings are root checks only.",
    ]
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
    if not integrity.empty:
        tex.insert(
            tex.index(r"\subsection{Performance Evaluation}"),
            f"Across the four datasets, {int(negatives.attempts.sum())} deliberately invalid inputs were tested with {int(negatives.unexpected.sum())} unexpected outcomes. These are implementation checks, not a substitute for the cryptographic security argument.",
        )
    if aggregates and not repeat.empty:
        performance_text = []
        for name in sorted(repeat.dataset.unique()):
            needed = {
                ("prove", "operation_seconds"),
                ("verify", "operation_seconds"),
                ("prove", "process_peak_rss_bytes"),
            }
            available = {
                (r["stage"], r["metric"]) for r in aggregates if r["dataset"] == name
            }
            if not needed <= available:
                continue

            def metric(phase, key):
                return next(
                    r
                    for r in aggregates
                    if r["dataset"] == name
                    and r["stage"] == phase
                    and r["metric"] == key
                )["mean"]

            performance_text.append(
                f"For {LABELS[name]}, mean proving time was {metric('prove', 'operation_seconds'):.3f} s "
                f"and mean verification time was {1000*metric('verify', 'operation_seconds'):.3f} ms. "
                f"The mean prover-process peak was {metric('prove', 'process_peak_rss_bytes')/1024**2:.1f} MiB."
            )
        pos = tex.index(r"\subsection{Scalability Analysis}")
        tex.insert(pos, " ".join(performance_text))
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
    captions = {
        "fig_utility": "Threshold outcomes at $K=0,1,2,3$. Blue squares at $K=1$ count verified Groth16 certificates; open blue circles at other thresholds count solver-satisfied cases, not certificates. Red crosses show the plaintext reference. The denominator includes every case in each cohort.",
        "fig_overhead": "Per-case mean operation overhead with sample-standard-deviation error bars over five paired repetitions. Dataset medians are calculated across selected case means, not across the whole population. The protected computation includes plaintext alignment, witness encoding, and proving. Setup and artifact loading are excluded from these operation times and recorded separately.",
        "fig_time_memory": "Mean operation time and mean per-process peak resident memory for witness encoding, proving, and verification on the selected cases. Error bars show sample standard deviation across the selected cases and repetitions, not only within-case variability. Each stage and repetition runs in a fresh process. Process peaks include loaded artifacts and serialization. Proving includes constraint solving.",
        "fig_setup_time_memory": "Compilation and setup measured independently in fresh processes, with five repetitions per model. Points and error bars show the mean and sample standard deviation. Time refers to the named operation, while resident memory is the peak of the complete worker process.",
        "fig_model_scalability": "Controlled model scaling for sequence, choice, parallel, and loop structures. Trace capacity is 128 and alignment capacity is 256 for every model. Proving times show the mean and sample standard deviation of three repetitions per model. Structural counts are supplied in the figure CSV.",
        "fig_capacity": "Effect of alignment capacity for the fixed Sepsis model and a trace capacity of 185. Coverage counts all held-out traces whose reference alignment fits, regardless of whether its cost meets the audit threshold.",
        "fig_trace_length": "Single functional-run proving times for certified Sepsis cases at fixed capacities, with selected-case repeated medians and minimum-to-maximum ranges overlaid. Repeated measurements are available for four selected cases only.",
        "fig_population": "Fresh-process root validation for synthetic rosters of distinct commitments, with means and sample-standard-deviation error bars over three repetitions. This experiment measures population-root checking, not verification of an equal number of proofs. Separate experiments audit 100 and 300 cases with 100 and 299 accepted certificates, respectively.",
    }
    figure_tex = [r"% Requires graphicx. Copy the accompanying figures directory."]
    for name, caption in captions.items():
        if (figures / (name + ".pdf")).exists():
            figure_tex += [
                r"\begin{figure}[t]\centering",
                r"\includegraphics[width=\linewidth]{figures/" + name + ".pdf}",
                r"\caption{" + caption + "}",
                r"\label{fig:eval-" + name.removeprefix("fig_") + "}",
                r"\end{figure}",
            ]
    (results / "evaluation_figures.tex").write_text("\n".join(figure_tex) + "\n")
    return figures


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    print(report(p.parse_args().root))
