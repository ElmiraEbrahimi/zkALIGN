import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval.capacity_performance import benchmark, summarize
from eval.data import save


class CapacityPerformanceTests(unittest.TestCase):
    def inputs(self, root):
        source = root / "source"
        save(source / "config.json", {"trace_capacity": 185, "alignment_capacity": 384})
        save(source / "cases.json", [{"case_id": "AG", "index": 10,
                                      "status": "aligned", "cost": 1,
                                      "events": [1], "moves": [{"type": 2}]}])
        binary = root / "binary"
        binary.write_bytes(b"fake worker for mocked test")
        return source, binary

    def worker(self, binary, folder, phase, **kwargs):
        self.assertEqual(kwargs["k"], 1)
        return dict(stage=phase, status="ok", operation_seconds=0.2,
                    process_peak_rss_bytes=12_000_000, constraints=100,
                    bytes={"pk": 50} if phase == "setup" else {})

    def test_all_stages_repeated_resume_and_changed_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, binary = self.inputs(root)
            output = root / "output"
            with patch("eval.capacity_performance.stage", side_effect=self.worker) as worker:
                benchmark(source, output, binary, (32, 64), 2, 1)
                self.assertEqual(worker.call_count, 28)
                benchmark(source, output, binary, (32, 64), 2, 1)
                self.assertEqual(worker.call_count, 28)
            with (output / "results/capacity_performance_summary.csv").open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(r["n_repetitions"] == "2" and r["complete"] == "True" for r in rows))
            self.assertTrue(all(float(r["mem_mean_mb"]) == 12 for r in rows))
            self.assertTrue(all(float(r["time_sd_s"]) == 0 for r in rows))
            binary.write_bytes(b"changed worker")
            with self.assertRaisesRegex(ValueError, "binary changed"):
                benchmark(source, output, binary, (32, 64), 2, 1)

    def test_failure_is_recorded_and_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, binary = self.inputs(root)
            output = root / "output"
            with patch("eval.capacity_performance.stage", return_value={"status": "error", "error": "test failure"}):
                with self.assertRaises(RuntimeError):
                    benchmark(source, output, binary, (32,), 2, 1)
            self.assertFalse((output / "capacity-32/repeat-1/complete.json").exists())
            self.assertIn("test failure", (output / "results/capacity_performance_runs.csv").read_text())

    def test_sample_sd_not_population_sd(self):
        common = dict(dataset="sepsis", case_id="AG", K=1, trace_capacity=185,
                      alignment_capacity=32, constraints=100, threads=1,
                      trace_length=5, alignment_length=18, stage="prove", status="ok")
        rows = [dict(common, operation_seconds=t, process_peak_rss_bytes=t*1_000_000)
                for t in (1, 3)]
        row = summarize(rows, 5)[0]
        self.assertAlmostEqual(row["time_sd_s"], 2**0.5)
        self.assertAlmostEqual(row["mem_sd_mb"], 2**0.5)
        self.assertFalse(row["complete"])


if __name__ == "__main__":
    unittest.main()
