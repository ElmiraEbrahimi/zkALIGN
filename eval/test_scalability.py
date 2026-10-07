import unittest
from eval.scalability import synthetic, replay


class SyntheticTests(unittest.TestCase):
    def test_all_control_flow_families_replay(self):
        for family in ("sequence", "choice", "parallel", "loop"):
            for n in (5, 10, 20, 30, 40, 50):
                cfg, c = synthetic(family, n)
                replay(cfg, c)
                self.assertEqual(cfg["trace_capacity"], 128)
                self.assertEqual(cfg["alignment_capacity"], 256)
                self.assertEqual(len(set(cfg["labels"]) - {0}), n)


if __name__ == "__main__":
    unittest.main()
