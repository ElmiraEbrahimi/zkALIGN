import unittest

from eval.above_threshold import classify, enrich_summary


class AboveThresholdTests(unittest.TestCase):
    def setUp(self):
        self.case = dict(dataset="sepsis", index=4, case_id="test", K=1,
                         reference_cost=2, mode="groth16")
        self.evidence = {**self.case, "solver_satisfied": False, "reason": "constraint_rejected"}
        self.summary = [dict(dataset="sepsis", K=1, N=2, reference_qualified=1)]

    def test_constraint_failure_is_rejection_but_execution_failure_is_not(self):
        base = dict(stage="solve", status="error", exit_code=1)
        self.assertEqual(classify({**base, "error": "constraint #42 is not satisfied: -1 * 1 != 0"}),
                         (False, "constraint_rejected"))
        for error in ("timeout", "capacity", "file not found", "panic"):
            self.assertEqual(classify({**base, "error": error}), ("", "solver_error"))
        self.assertEqual(classify(dict(stage="solve", status="ok", exit_code=0)),
                         (True, "constraint_satisfied"))
        with self.assertRaises(ValueError):
            classify(dict(stage="prove"))

    def test_complete_counts_and_no_negative_cases(self):
        rows = enrich_summary(self.summary, [self.case], [self.evidence])
        self.assertEqual(rows[0]["above_threshold_cases"], 1)
        self.assertEqual(rows[0]["above_threshold_rejected"], 1)
        self.assertNotIn("above_threshold_cases", self.summary[0])
        empty = enrich_summary([dict(dataset="sepsis", K=3, N=2, reference_qualified=2)], [], [])
        self.assertEqual(empty[0]["above_threshold_cases"], 0)
        self.assertEqual(empty[0]["above_threshold_rejected"], 0)

    def test_missing_duplicate_wrong_cost_or_id_fail(self):
        for evidence in ([], [self.evidence, self.evidence],
                         [{**self.evidence, "case_id": "wrong"}],
                         [{**self.evidence, "reference_cost": 3}],
                         [{**self.evidence, "solver_satisfied": True}]):
            with self.assertRaises(ValueError):
                enrich_summary(self.summary, [self.case], evidence)

    def test_unexpected_success_and_errors_not_counted_as_rejection(self):
        for reason, flag in (("constraint_satisfied", True), ("solver_error", "")):
            rows = enrich_summary(self.summary, [self.case],
                                  [{**self.evidence, "reason": reason, "solver_satisfied": flag}])
            self.assertEqual(rows[0]["above_threshold_cases"], 1)
            self.assertEqual(rows[0]["above_threshold_rejected"], 0)


if __name__ == "__main__":
    unittest.main()
