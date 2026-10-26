"""Regression checks for benchmark defaults and saved-result compatibility."""

import inspect
from pathlib import Path
import unittest

import pandas as pd

from eval import scalability
from eval.capacity_performance import benchmark
from eval.performance_rerun_v2 import run_suite
from eval.plotting.overhead import validate


class RepetitionTests(unittest.TestCase):
    def test_benchmark_defaults_are_ten(self):
        for name in ("experiment", "models", "capacities", "repeats", "setup_repeats", "population"):
            self.assertEqual(inspect.signature(getattr(scalability, name)).parameters["repeat"].default, 10)
        for fn in (benchmark, run_suite):
            self.assertEqual(inspect.signature(fn).parameters["repetitions"].default, 10)

    def test_overhead_accepts_ten_and_rejects_missing_repeat(self):
        results = Path(__file__).parent / "results"
        pairs = pd.read_csv(results / "overhead.csv")
        timings = pd.read_csv(results / "repeated_timings.csv")
        summary = pd.read_csv(results / "overhead_summary.csv")
        summary = summary[summary.scope == "case"].copy()
        validate(pairs, timings, summary)
        # Duplicate fixture observations with new indices, not real measurements.
        def doubled(frame):
            extra = frame.copy()
            extra["repeat"] += 5
            return pd.concat([frame, extra], ignore_index=True)
        pairs, timings = doubled(pairs), doubled(timings)
        for i, row in summary.iterrows():
            group = pairs[(pairs.dataset == row.dataset) & (pairs["index"] == row["index"])]
            summary.loc[i, "n"] = len(group)
            for metric in ("plaintext_alignment_seconds", "prover_operation_seconds", "operation_overhead"):
                summary.loc[i, metric + "_mean"] = group[metric].mean()
                summary.loc[i, metric + "_sd"] = group[metric].std(ddof=1)
        validate(pairs, timings, summary)
        with self.assertRaises(ValueError):
            validate(pairs.iloc[:-1], timings, summary)
