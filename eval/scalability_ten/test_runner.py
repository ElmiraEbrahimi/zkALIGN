"""Mocked safety checks; no real proof generation."""
from contextlib import redirect_stdout
import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import __main__ as runner
from .__main__ import FILES, run, schedule, summaries


class TenRunTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "old"
        folder = source / "loop-40"
        (folder / "measurements").mkdir(parents=True)
        for name in FILES:
            (folder / name).write_text("fixture")
        (folder / "measurements/compile.json").write_text('{"status":"ok","constraints":233016}')
        binary = root / "binary"
        binary.write_text("fake")
        spec = dict(family="loop", activities=40, source=folder, places=5,
                    transitions=5, arcs=10, constraints=233016, trace_capacity=128,
                    alignment_capacity=256, pk_bytes=7)
        return source, binary, [spec]

    def fake(self, binary, folder, phase, **kwargs):
        result = dict(status="ok", exit_code=0, operation_seconds=.4,
                      worker_seconds=1.1, process_peak_rss_bytes=600_000_000,
                      user_cpu_seconds=.8, system_cpu_seconds=.1, pid=123,
                      measurement_file=str(folder / kwargs["tag"]), gomaxprocs=14)
        if phase == "verify":
            result["details"] = {"certified":1}
        return result

    def test_randomized_ten_complete_blocks(self):
        jobs = schedule([{}] * 24, 81)
        self.assertEqual(jobs, schedule([{}] * 24, 81))
        self.assertEqual(len(jobs), 240)
        for repeat in range(1, 11):
            self.assertEqual(sorted(j["spec"] for j in jobs if j["repeat"] == repeat), list(range(24)))
        self.assertEqual([j["order"] for j in jobs], list(range(1, 241)))

    def test_separate_runs_and_originals_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, binary, specs = self.fixture(root)
            original = {p:p.read_bytes() for p in source.rglob("*") if p.is_file()}
            with patch.object(runner, "read_specs", return_value=specs), \
                 patch.object(runner, "stage", side_effect=self.fake) as calls, \
                 redirect_stdout(io.StringIO()):
                first = run(source, root / "new", binary)
                saved = {p:p.read_bytes() for p in first.rglob("*") if p.is_file()}
                second = run(source, root / "new", binary)
            self.assertNotEqual(first, second)
            self.assertEqual(calls.call_count, 60)
            self.assertEqual(original, {p:p.read_bytes() for p in original})
            self.assertEqual(saved, {p:p.read_bytes() for p in saved})
            with (first / "ten_scalability_runs.csv").open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 30)
            with (first / "ten_model_scalability.csv").open() as stream:
                result = next(csv.DictReader(stream))
            self.assertEqual(result["n"], "10")
            self.assertEqual(result["verified_proofs"], "10")
            self.assertEqual(float(result["prove_memory_mb_mean"]), 600)
            self.assertEqual(float(result["prove_seconds_mean"]), .4)
            self.assertTrue((first / "ten_complete.json").exists())

    def test_failed_verification_cannot_publish_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, binary, specs = self.fixture(root)
            def invalid(*args, **kwargs):
                result = self.fake(*args, **kwargs)
                result["details"] = {"certified":0}
                return result
            with patch.object(runner, "read_specs", return_value=specs), \
                 patch.object(runner, "stage", side_effect=invalid), \
                 redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    run(source, root / "new", binary)
            folder = next((root / "new").iterdir())
            self.assertTrue((folder / "ten_failed.json").exists())
            self.assertFalse((folder / "ten_complete.json").exists())
            self.assertFalse((folder / "ten_model_scalability.csv").exists())

    def test_missing_input_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                run(root / "absent", root / "new", root / "binary")
            self.assertFalse((root / "new").exists())

    def test_incomplete_summary_rejected(self):
        with self.assertRaises(ValueError):
            summaries([dict(family="loop", activities=40)],
                      [dict(family="loop", activities=40, threads=14, stage="prove", status="ok")])


if __name__ == "__main__":
    unittest.main()
