import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from eval.data import DATASETS, save
from eval.run import csv_write
from eval.publish import check_experiments, publish


class PublicationTests(unittest.TestCase):
    def test_export_allowlist_excludes_extra_files_and_normalizes_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            results = root / "results"
            (results / "figures").mkdir(parents=True)
            (results / "utility_cases.csv").write_bytes(b"index\r\n0\r\n")
            (results / "unexpected.csv").write_text("not a published artifact")
            for name in DATASETS:
                save(
                    root / "data" / name / "measurements/audit-k1.json",
                    {"details": {"population": 1, "certified": 1}},
                )
            destination = Path(tmp) / "published"
            with (
                patch(
                    "eval.publish.validate",
                    return_value=[
                        {"K": 1, "mode": "groth16"},
                        {"K": 2, "mode": "groth16"},
                        {"K": 0, "mode": "solver"},
                    ],
                ),
                patch("eval.publish.check_experiments"),
                patch("eval.publish.report"),
            ):
                publish(root, destination)
            self.assertEqual(
                (destination / "utility_cases.csv").read_bytes(), b"index\n0\n"
            )
            self.assertFalse((destination / "unexpected.csv").exists())
            import json

            provenance = json.loads((destination / "provenance.json").read_text())
            self.assertEqual(provenance["real_proof_thresholds"], [1, 2])
            self.assertEqual(provenance["solver_only_thresholds"], [0])

    def fixture(self, root):
        out = root / "results"
        csv_write(
            out / "repeated_timings.csv",
            [
                dict(dataset=d, threads=t, index=0, stage=s, repeat=r, status="ok")
                for d in DATASETS
                for t in ("1", "default")
                for s in ("witness", "prove", "verify")
                for r in range(5)
            ],
        )
        csv_write(
            out / "repeated_setup.csv",
            [
                dict(dataset=d, stage=s, repeat=r, status="ok")
                for d in DATASETS
                for s in ("compile", "setup")
                for r in range(5)
            ],
        )
        csv_write(
            out / "scal_model.csv",
            [
                dict(family=f, activities=n, stage=s, repeat=r, status="ok")
                for f in ("sequence", "choice", "parallel", "loop")
                for n in (5, 10, 20, 30, 40, 50)
                for s in ("witness", "prove", "verify")
                for r in range(3)
            ],
        )
        csv_write(
            out / "scal_capacity.csv",
            [
                dict(alignment_capacity=n, stage=s, repeat=r, status="ok")
                for n in (32, 64, 128, 256, 384)
                for s in ("witness", "prove", "verify")
                for r in range(3)
            ],
        )
        csv_write(
            out / "scal_population.csv",
            [
                dict(N=n, repeat=r, status="ok")
                for n in (100, 1000, 10000, 100000)
                for r in range(3)
            ],
        )
        csv_write(
            out / "scal_population_proofs.csv",
            [
                dict(N=n, mode="real_distinct_certificates", status="ok")
                for n in (100, 300)
            ],
        )
        csv_write(
            out / "integrity.csv", [dict(dataset=d, unexpected=0) for d in DATASETS]
        )

    def test_complete_experiments_pass_and_failed_integrity_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            check_experiments(root)
            csv_write(
                root / "results/integrity.csv",
                [dict(dataset=d, unexpected=1) for d in DATASETS],
            )
            with self.assertRaises(ValueError):
                check_experiments(root)

    def test_partial_repeated_measurements_block_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            csv_write(
                root / "results/repeated_setup.csv",
                [dict(dataset="sepsis", stage="setup", repeat=0, status="ok")],
            )
            with self.assertRaises(ValueError):
                check_experiments(root)
