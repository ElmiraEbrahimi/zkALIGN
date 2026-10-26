"""Summarize saved measurements and generate evaluation plots."""

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
        "# Evaluation results", "",
        "Summaries and figures generated from saved measurements.", "",
        "- Utility: utility_summary.csv and utility_cases.csv.",
        "- Performance: performance_summary.csv and repeated_timings.csv.",
        "- Compilation/setup: setup_summary.csv and repeated_setup.csv.",
        "- Scalability: scal_model_summary.csv and scal_*.csv.",
        "- Integrity: integrity.csv.", "",
        "Operation times exclude startup, loading, and serialization. Worker times include them.",
        "Raw RSS values are bytes; plots use decimal MB and whole-process peaks.",
        "Error bars show sample standard deviations. Solver checks are not verified proofs.",
    ]

    def read(name):
        p = results / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

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
            & (cases.K == 1)
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
    return figures


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    print(report(p.parse_args().root))
