"""Validate and redraw the selected-case operation-overhead figure only."""

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from .draw import overhead


def validate(pairs, timings, summary):
    timings = timings[timings.threads.astype(str) == "default"]
    keys = ["dataset", "index", "repeat"]
    if pairs.duplicated(keys).any() or timings.duplicated(keys + ["stage"]).any():
        raise ValueError("Duplicate repeated measurements")
    if not timings.status.eq("ok").all():
        raise ValueError("Failed timing observation")
    if set(map(tuple, pairs[keys].to_numpy())) != set(map(tuple, timings[keys].to_numpy())):
        raise ValueError("Unmatched paired observations")
    counts = pairs.groupby(["dataset", "index"]).size()
    if not counts.eq(5).all() or counts.groupby(level=0).size().to_dict() != {
        "bpic13cp": 3, "hospital": 3, "rtfm": 3, "sepsis": 4,
    }:
        raise ValueError("Expected five paired repeats for the 13 selected cases")
    if summary.duplicated(["dataset", "index"]).any() or len(summary) != 13:
        raise ValueError("Invalid selected-case summary")
    indexed = pairs.set_index(keys)
    for key, group in timings.groupby(keys):
        g = group.set_index("stage")
        if set(g.index) != {"alignment", "witness", "prove", "verify"}:
            raise ValueError("Missing timing stage")
        plain = g.loc["alignment", "operation_seconds"]
        protected = plain + g.loc["witness", "operation_seconds"] + g.loc["prove", "operation_seconds"]
        row = indexed.loc[key]
        if plain <= 0 or not np.allclose(
            row[["plaintext_alignment_seconds", "prover_operation_seconds", "operation_overhead"]].to_numpy(dtype=float),
            [plain, protected, protected/plain], rtol=1e-9, atol=1e-12,
        ):
            raise ValueError("Overhead pair disagrees with raw stage timings")
    indexed_summary = summary.set_index(["dataset", "index"])
    for key, g in pairs.groupby(["dataset", "index"]):
        row = indexed_summary.loc[key]
        if row["n"] != 5:
            raise ValueError("Incorrect repetition count")
        for metric in ("plaintext_alignment_seconds", "prover_operation_seconds", "operation_overhead"):
            if not np.allclose([row[metric+"_mean"], row[metric+"_sd"]],
                               [g[metric].mean(), g[metric].std(ddof=1)], rtol=1e-9, atol=1e-12):
                raise ValueError("Overhead summary disagrees with paired repeats")
    for _, g in summary.groupby("dataset"):
        if not np.allclose(g.dataset_median_case_overhead, g.operation_overhead_mean.median()):
            raise ValueError("Incorrect median of selected case means")


def generate(results, data, figures):
    results, data, figures = map(Path, (results, data, figures))
    pairs = pd.read_csv(results / "overhead.csv")
    timings = pd.read_csv(results / "repeated_timings.csv")
    summary = pd.read_csv(results / "overhead_summary.csv")
    frame = summary[summary.scope == "case"].copy()
    validate(pairs, timings, frame)
    frame["source_pairs"] = str(results / "overhead.csv")
    frame["source_timings"] = str(results / "repeated_timings.csv")
    frame["K"] = 1
    frame["time_scope"] = "operation only; excludes startup, key loading, output, setup and verification"
    frame["ratio_definition"] = "(alignment + input-witness encoding + proving) / alignment"
    frame["error_bar"] = "sample SD of five per-repeat ratios"
    data.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    csv = data / "fig_overhead.csv"
    frame.to_csv(csv, index=False)
    overhead(pd.read_csv(csv), figures / "fig_overhead.pdf")
    print("Validated 65 paired repeats across 13 selected cases; overhead PDF and CSV saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("eval/results"))
    parser.add_argument("--data", type=Path, default=Path("eval/plotting/data"))
    parser.add_argument("--figures", type=Path, default=Path("eval/results/figures"))
    args = parser.parse_args()
    generate(args.results, args.data, args.figures)
