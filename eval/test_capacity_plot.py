import unittest

import pandas as pd

from eval.capacity_performance import summarize
from eval.plotting.capacity_performance import BOUNDS, STAGES, validate, elapsed_summary


class CapacityPlotTests(unittest.TestCase):
    def setUp(self):
        rows = [dict(dataset="sepsis", case_id="AG", K=1, trace_capacity=185,
                     trace_length=5, alignment_length=18, threads=14, gomaxprocs=14,
                     alignment_capacity=b, constraints=b*100, stage=s, repeat=r,
                     status="ok", operation_seconds=r/10, worker_seconds=2.0*r,
                     process_peak_rss_bytes=1_000_000*r)
                for b in BOUNDS for s in STAGES for r in range(1, 6)]
        self.runs = pd.DataFrame(rows)
        self.summary = pd.DataFrame(summarize(rows, 5))

    def test_complete_run(self):
        validate(self.runs, self.summary)

    def test_missing_and_duplicate_runs_rejected(self):
        for rows in (self.runs.iloc[:-1], pd.concat([self.runs, self.runs.iloc[:1]])):
            with self.assertRaises(ValueError):
                validate(rows, self.summary)

    def test_bad_summary_rejected(self):
        self.summary.loc[0, "time_sd_s"] = 999
        with self.assertRaisesRegex(ValueError, "disagrees"):
            validate(self.runs, self.summary)

    def test_failed_verification_rejected(self):
        self.runs.loc[self.runs.stage == "verify", "status"] = "error"
        with self.assertRaisesRegex(ValueError, "failed"):
            validate(self.runs, self.summary)

    def test_changed_input_rejected(self):
        self.runs.loc[0, "K"] = 2
        with self.assertRaisesRegex(ValueError, "Controlled input"):
            validate(self.runs, self.summary)

    def test_whole_stage_mean_and_sd_are_not_operation_values(self):
        result = elapsed_summary(self.runs, self.summary)
        self.assertTrue((result.worker_time_mean_s == 6).all())
        self.assertAlmostEqual(result.worker_time_sd_s.iloc[0], 10**0.5)
        self.assertAlmostEqual(result.operation_time_mean_s.iloc[0], 0.3)
        self.assertTrue((result.plotted_time_metric == "worker_seconds").all())
        self.assertNotIn("time_mean_s", result.columns)

    def test_impossible_time_scope_rejected(self):
        self.runs.loc[0, "worker_seconds"] = 0.0001
        with self.assertRaisesRegex(ValueError, "Whole-stage"):
            validate(self.runs, self.summary)


if __name__ == "__main__":
    unittest.main()
