import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from eval.data import save
from eval.scalability import synthetic, replay, real_population


class SyntheticTests(unittest.TestCase):
    def test_all_control_flow_families_replay(self):
        for family in ("sequence", "choice", "parallel", "loop"):
            for n in (5, 10, 20, 30, 40, 50):
                cfg, c = synthetic(family, n)
                replay(cfg, c)
                self.assertEqual(cfg["trace_capacity"], 128)
                self.assertEqual(cfg["alignment_capacity"], 256)
                self.assertEqual(len(set(cfg["labels"]) - {0}), n)

    def test_population_benchmark_uses_distinct_prefix_and_checks_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root / "data/rtfm/config.json", {"example": True})
            save(
                root / "data/rtfm/cases.json",
                [{"index": i, "cost": 0 if i < 99 else 2} for i in range(300)],
            )

            def fake_audit(binary, folder, stage_name, **kwargs):
                n = 300 if folder.name == "rtfm" else 100
                return {
                    "status": "ok",
                    "details": {
                        "population": n,
                        "certified": 99,
                        "required": n * 95 // 100,
                    },
                }

            with (
                patch("eval.scalability.evaluate") as evaluate,
                patch("eval.scalability.stage", side_effect=fake_audit),
            ):
                real_population(root)
                evaluate.assert_called_once()
            subset = json.loads(
                (root / "population-audits/rtfm-100/cases.json").read_text()
            )
            self.assertEqual([c["index"] for c in subset], list(range(100)))
            with (
                patch("eval.scalability.evaluate"),
                patch(
                    "eval.scalability.stage",
                    return_value={
                        "status": "ok",
                        "details": {"population": 100, "certified": 100},
                    },
                ),
            ):
                with self.assertRaises(ValueError):
                    real_population(root)


if __name__ == "__main__":
    unittest.main()
