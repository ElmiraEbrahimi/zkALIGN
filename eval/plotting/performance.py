"""Redraw only the two performance figures from saved repeated benchmarks."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .draw import DRAW


def generate(results, data, figures):
    results, data, figures = map(Path, (results, data, figures))
    data.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    for name, source, stages in (
        ("fig_setup_time_memory", "setup_summary.csv", ("compile", "setup")),
        ("fig_time_memory", "performance_summary.csv", ("witness", "prove")),
    ):
        frame = pd.read_csv(results / source)
        frame = frame[frame.stage.isin(stages) & frame.metric.isin(
            ("operation_seconds", "process_peak_rss_bytes"))].copy()
        expected = {(dataset, stage, metric)
                    for dataset in ("bpic13cp", "rtfm", "sepsis", "hospital")
                    for stage in stages
                    for metric in ("operation_seconds", "process_peak_rss_bytes")}
        keys = list(zip(frame.dataset, frame.stage, frame.metric))
        if len(keys) != len(expected) or set(keys) != expected:
            raise ValueError(f"{source}: missing or duplicate plotted measurements")
        if not np.isfinite(frame[["mean", "std", "n"]].to_numpy()).all():
            raise ValueError(f"{source}: non-finite measurement")
        if (frame.n < 2).any() or (frame["std"] < 0).any() or (
            frame["mean"] - frame["std"] <= 0
        ).any():
            raise ValueError(f"{source}: invalid repeat count or logarithmic error bar")
        frame["source_summary"] = source
        frame["error_bar"] = "sample_standard_deviation"
        frame["memory_unit_in_csv"] = "bytes"
        frame["memory_unit_in_figure"] = "MB (1000000 bytes)"
        frame.to_csv(data / f"{name}.csv", index=False)
        DRAW[name](pd.read_csv(data / f"{name}.csv"), figures / f"{name}.pdf")
        print(f"{name}: {len(frame)} measured means with SD; PDF and source CSV saved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("eval/results"))
    parser.add_argument("--data", type=Path, default=Path("eval/plotting/data"))
    parser.add_argument("--figures", type=Path, default=Path("eval/results/figures"))
    args = parser.parse_args()
    generate(args.results, args.data, args.figures)
