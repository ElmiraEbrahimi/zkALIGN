import tempfile
import unittest
from pathlib import Path
from eval.report import report
from eval.run import csv_write


class ReportTests(unittest.TestCase):
    def test_incomplete_run_is_not_plotted_as_complete_utility(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "results"
            p.mkdir()
            csv_write(
                p / "utility_summary.csv",
                [
                    {
                        "dataset": "sepsis",
                        "K": 1,
                        "mode": "groth16",
                        "N": 210,
                        "processed": 2,
                        "reference_qualified": 200,
                        "certified": 2,
                        "errors": 0,
                        "reference_share": 200 / 210,
                        "certified_share": 2 / 210,
                    }
                ],
            )
            report(tmp)
            self.assertFalse((p / "figures/fig_utility.pdf").exists())
            self.assertIn("incomplete", (p / "README.md").read_text())
            self.assertNotIn("2 of 210", (p / "evaluation_results.tex").read_text())


if __name__ == "__main__":
    unittest.main()
