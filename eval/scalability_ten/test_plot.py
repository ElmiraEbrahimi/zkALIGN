"""Read-only checks against the completed run, plus corrupted-input guards."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from . import plot


@unittest.skipUnless(os.environ.get("TEN_PLOT_TEST_RUN"), "Set TEN_PLOT_TEST_RUN to a completed run")
class PlotValidationTests(unittest.TestCase):
    def setUp(self):
        self.run = Path(os.environ["TEN_PLOT_TEST_RUN"])

    def test_completed_run(self):
        self.assertEqual(len(plot.validated_data(self.run)), 24)

    def test_duplicate_rejected(self):
        read = plot.read_csv
        def duplicate(path):
            rows = read(path)
            if path.name == "ten_scalability_runs.csv":
                rows[1] = rows[0].copy()
            return rows
        with patch.object(plot, "read_csv", side_effect=duplicate):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                plot.validated_data(self.run)

    def test_changed_mean_rejected(self):
        read = plot.read_csv
        def changed(path):
            rows = read(path)
            if path.name == "ten_model_scalability.csv":
                rows[0]["prove_seconds_mean"] = "10"
            return rows
        with patch.object(plot, "read_csv", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Summary disagrees"):
                plot.validated_data(self.run)


if __name__ == "__main__":
    unittest.main()
