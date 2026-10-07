import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd

from eval.summaries import (
    utility_metrics,
    enrich_utility,
    overhead_summary,
    model_summary,
    trace_summary,
)
from eval.report import report


class SummaryTests(unittest.TestCase):
    def test_solver_errors_are_not_rejections_or_agreement(self):
        rows = [
            {
                "reason": "constraint_satisfied",
                "solver_satisfied": True,
                "reference_ok": True,
            },
            {
                "reason": "constraint_rejected",
                "solver_satisfied": False,
                "reference_ok": False,
            },
            {
                "reason": "solver_error",
                "solver_satisfied": False,
                "reference_ok": False,
            },
        ]
        result = utility_metrics(rows, "solver")
        self.assertEqual(result["solver_satisfied"], 1)
        self.assertEqual(result["solver_rejected"], 1)
        self.assertEqual(result["agreement_cases"], 2)
        self.assertEqual(result["agreement_unavailable"], 1)
        self.assertEqual(result["agreement_pct"], 100)

    def test_disagreement_is_counted_and_solver_is_not_certified(self):
        cases = pd.DataFrame(
            [
                {
                    "dataset": "x",
                    "K": 0,
                    "mode": "solver",
                    "reason": "constraint_rejected",
                    "solver_satisfied": False,
                    "reference_ok": True,
                }
            ]
        )
        summary = pd.DataFrame(
            [
                {
                    "dataset": "x",
                    "K": 0,
                    "mode": "solver",
                    "processed": 1,
                    "certified": 0.0,
                    "certified_share": 0.0,
                }
            ]
        )
        out = enrich_utility(summary, cases).iloc[0]
        self.assertEqual(out.agreement_pct, 0)
        self.assertTrue(pd.isna(out.certified))
        self.assertTrue(pd.isna(out.certified_share))

    def test_overhead_is_mean_of_paired_ratios_and_median_of_case_means(self):
        cases = pd.DataFrame(
            [
                {
                    "dataset": "x",
                    "index": i,
                    "case_id": str(i),
                    "K": 1,
                    "mode": "groth16",
                    "reference_ok": True,
                    "alignment_length": i + 1,
                    "trace_length": 1,
                }
                for i in range(2)
            ]
        )
        pairs = pd.DataFrame(
            [
                {
                    "dataset": "x",
                    "index": 0,
                    "plaintext_alignment_seconds": 1.0,
                    "prover_operation_seconds": 2.0,
                    "operation_overhead": 2.0,
                },
                {
                    "dataset": "x",
                    "index": 0,
                    "plaintext_alignment_seconds": 2.0,
                    "prover_operation_seconds": 8.0,
                    "operation_overhead": 4.0,
                },
                {
                    "dataset": "x",
                    "index": 1,
                    "plaintext_alignment_seconds": 1.0,
                    "prover_operation_seconds": 10.0,
                    "operation_overhead": 10.0,
                },
                {
                    "dataset": "x",
                    "index": 1,
                    "plaintext_alignment_seconds": 1.0,
                    "prover_operation_seconds": 10.0,
                    "operation_overhead": 10.0,
                },
            ]
        )
        out = overhead_summary(pairs, cases)
        first = out[(out.scope == "case") & (out["index"] == 0)].iloc[0]
        self.assertEqual(first.operation_overhead_mean, 3)
        self.assertAlmostEqual(first.operation_overhead_sd, 2**0.5)
        self.assertEqual(first.dataset_median_case_overhead, 6.5)
        self.assertEqual(len(out[out.scope == "case"]), 2)

    def test_model_counts_and_sample_sd(self):
        raw = pd.DataFrame(
            [
                {
                    "family": "parallel",
                    "activities": 40,
                    "stage": "prove",
                    "places": 82,
                    "transitions": 42,
                    "arcs": 160,
                    "constraints": 100,
                    "trace_capacity": 128,
                    "alignment_capacity": 256,
                    "pk_bytes": 5,
                    "operation_seconds": v,
                }
                for v in [1.0, 2.0, 3.0]
            ]
        )
        row = model_summary(raw).iloc[0]
        self.assertEqual(
            (row.places, row.transitions, row.arcs, row.n), (82, 42, 160, 3)
        )
        self.assertEqual(row.prove_seconds_mean, 2)
        self.assertEqual(row.prove_seconds_sd, 1)

    def test_repeated_trace_summary_does_not_invent_unsampled_cases(self):
        cases = pd.DataFrame(
            [
                {
                    "dataset": "sepsis",
                    "index": i,
                    "case_id": str(i),
                    "K": 1,
                    "mode": "groth16",
                    "reference_ok": True,
                    "alignment_length": i + 1,
                    "trace_length": 1,
                }
                for i in range(2)
            ]
        )
        raw = pd.DataFrame(
            [
                {
                    "dataset": "sepsis",
                    "index": 0,
                    "threads": "default",
                    "stage": "prove",
                    "operation_seconds": v,
                }
                for v in [1.0, 2.0, 5.0]
            ]
        )
        result = trace_summary(raw, cases)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0].prove_seconds_median, 2)
        self.assertEqual(result.iloc[0].prove_seconds_max, 5)

    def test_readme_uses_repeated_setup_and_never_runs_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "results"
            results.mkdir()
            pd.DataFrame(
                [
                    {
                        "dataset": "sepsis",
                        "stage": "setup",
                        "metric": "operation_seconds",
                        "n": 5,
                        "mean": 8.763499,
                        "std": 0.12526,
                    }
                ]
            ).to_csv(results / "setup_summary.csv", index=False)
            with (
                patch("eval.report.generate_figures"),
                patch(
                    "eval.measure.stage", side_effect=AssertionError("worker called")
                ),
            ):
                report(tmp)
            text = (results / "README.md").read_text()
            self.assertIn("8.76 s (SD 0.13)", text)
            self.assertNotIn("33.8", text)


if __name__ == "__main__":
    unittest.main()
