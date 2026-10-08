import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval.data import save
from eval.run import evaluate


class RealThresholdTests(unittest.TestCase):
    def fixture(self, folder):
        save(
            folder / "cases.json",
            [
                dict(
                    index=0,
                    case_id="a",
                    cost=1,
                    events=[1],
                    moves=[{}],
                    status="aligned",
                    alignment_seconds=0.01,
                )
            ],
        )
        save(folder / "config.json", dict(trace_capacity=1, alignment_capacity=1))

    def test_defaults_prove_all_thresholds_and_audit_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.fixture(folder)
            calls = []

            def worker(binary, path, phase, **kw):
                calls.append((phase, kw["k"]))
                return dict(
                    status="ok",
                    process_peak_rss_bytes=1,
                    worker_seconds=0.01,
                    operation_seconds=0.01,
                    details=dict(certified=int(kw["k"] >= 1)),
                )

            with (
                patch("eval.run.initialize"),
                patch("eval.run.stage", side_effect=worker),
            ):
                evaluate(folder)
            rows = json.loads((folder / "utility.json").read_text())
            self.assertEqual([r["K"] for r in rows], [0, 1, 2, 3])
            self.assertTrue(all(r["mode"] == "groth16" for r in rows))
            self.assertEqual(rows[0]["reason"], "above_threshold")
            self.assertEqual([k for phase, k in calls if phase == "prove"], [1, 2, 3])
            self.assertEqual(
                [k for phase, k in calls if phase == "audit"], [0, 1, 2, 3]
            )
            self.assertNotIn("solve", [phase for phase, _ in calls])

    def test_interruption_preserves_existing_proofs_and_archives_solver(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.fixture(folder)
            old = [
                dict(index=0, K=1, mode="groth16", reason="certified", certified=True),
                dict(index=0, K=0, mode="solver", reason="constraint_rejected"),
            ]
            save(folder / "utility.json", old)

            def interrupted(binary, path, phase, **kw):
                if phase == "audit":
                    raise RuntimeError("interrupted")
                return dict(status="ok")

            with (
                patch("eval.run.initialize"),
                patch("eval.run.stage", side_effect=interrupted),
            ):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    evaluate(folder)
            rows = json.loads((folder / "utility.json").read_text())
            self.assertIn(old[0], rows)
            self.assertEqual(
                json.loads((folder / "utility-before-groth16.json").read_text()), old
            )


if __name__ == "__main__":
    unittest.main()
