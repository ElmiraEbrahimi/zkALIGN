import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval.data import DATASETS, save
from eval.validate import validate


class UtilityValidationTests(unittest.TestCase):
    def fixture(self, root):
        for name in DATASETS:
            folder = root / "data" / name
            save(folder / "cases.json", [dict(index=0)])
            save(
                folder / "utility.json",
                [
                    dict(
                        index=0,
                        K=k,
                        mode="groth16",
                        reason="certified",
                        certified=True,
                        reference_ok=True,
                    )
                    for k in range(4)
                ],
            )
            for k in range(4):
                save(
                    folder / f"measurements/audit-k{k}.json",
                    dict(details=dict(population=1, certified=1)),
                )

    def check(self, root):
        with (
            patch("eval.validate.collect", return_value=[]),
            patch("eval.validate.initialize"),
        ):
            return validate(root)

    def test_all_four_real_thresholds_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            self.check(root)
            name = next(iter(DATASETS))
            save(
                root / "data" / name / "utility.json",
                [
                    dict(
                        index=0,
                        K=k,
                        mode="groth16" if k == 1 else "solver",
                        reason="certified" if k == 1 else "constraint_satisfied",
                        certified=k == 1,
                        solver_satisfied=True,
                        reference_ok=True,
                    )
                    for k in range(4)
                ],
            )
            with self.assertRaisesRegex(
                ValueError, "threshold 0 real proof experiment incomplete"
            ):
                self.check(root)

    def test_auditor_checked_at_nondefault_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            name = next(iter(DATASETS))
            save(
                root / "data" / name / "measurements/audit-k3.json",
                dict(details=dict(population=1, certified=0)),
            )
            with self.assertRaisesRegex(ValueError, "auditor report inconsistent"):
                self.check(root)


if __name__ == "__main__":
    unittest.main()
