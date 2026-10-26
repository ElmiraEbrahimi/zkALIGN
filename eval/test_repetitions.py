"""Regression checks for benchmark defaults and saved-result compatibility."""

import inspect
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
        # Synthetic fixture: tests must not depend on local benchmark outputs.
        pair_rows, timing_rows, summary_rows = [], [], []
        for dataset, cases in (("bpic13cp", 3), ("hospital", 3), ("rtfm", 3), ("sepsis", 4)):
            for index in range(cases):
                for repeat in range(5):
                    key = dict(dataset=dataset, index=index, repeat=repeat)
                    pair_rows.append(dict(**key, plaintext_alignment_seconds=1.,
                                          prover_operation_seconds=2., operation_overhead=2.))
                    for stage, seconds in (("alignment", 1.), ("witness", .25), ("prove", .75), ("verify", .01)):
                        timing_rows.append(dict(**key, stage=stage, operation_seconds=seconds,
                                                threads="default", status="ok"))
                row = dict(dataset=dataset, index=index, n=5, dataset_median_case_overhead=2.)
                for metric, mean in (("plaintext_alignment_seconds", 1.), ("prover_operation_seconds", 2.), ("operation_overhead", 2.)):
                    row[metric + "_mean"] = mean
                    row[metric + "_sd"] = 0.
                summary_rows.append(row)
        pairs, timings, summary = map(pd.DataFrame, (pair_rows, timing_rows, summary_rows))
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
