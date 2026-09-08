from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from zkalign.alignment import find_min_cost_alignment
from zkalign.commitment import commit_trace
from zkalign.model import load_model
from zkalign.types import AlignmentMove
from zkalign.verifier import PublicStatement, verify_witness

ROOT = Path(__file__).resolve().parents[1]


class ReferenceVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = load_model(ROOT / "model" / "healthcare_fsm.json")
        self.trace = ["Admit", "Examine", "EmergencyTest", "Treat", "Discharge"]
        self.salt = bytes.fromhex("00112233445566778899aabbccddeeff")
        self.moves = find_min_cost_alignment(self.trace, self.model)
        commitment = commit_trace([self.model.activities[a] for a in self.trace], self.salt)
        self.statement = PublicStatement(commitment, self.model.version, 2, 2)

    def verify(self, **changes):
        return verify_witness(
            changes.get("trace", self.trace),
            changes.get("salt", self.salt),
            changes.get("moves", self.moves),
            self.model,
            changes.get("statement", self.statement),
        )

    def test_valid_healthcare_alignment_passes_all_six_checks(self):
        result = self.verify()
        self.assertTrue(result.accepted, result.errors)
        self.assertEqual(2, result.calculated_cost)

    def test_goal_1_rejects_trace_substitution(self):
        changed = ["Admit", "Examine", "Approve", "Treat", "Discharge"]
        self.assertFalse(self.verify(trace=changed).binding)

    def test_goal_2_rejects_alignment_for_another_trace(self):
        bad = list(self.moves)
        bad[2] = AlignmentMove.log("Approve")
        result = self.verify(moves=bad)
        self.assertFalse(result.trace_consistency)

    def test_goal_3_rejects_illegal_model_transition(self):
        bad = list(self.moves)
        bad[0] = AlignmentMove.sync("Admit", 2)
        result = self.verify(moves=bad)
        self.assertFalse(result.move_legality)

    def test_goal_4_rejects_incomplete_alignment(self):
        result = self.verify(moves=self.moves[:-1])
        self.assertFalse(result.completeness)

    def test_goal_5_rejects_false_cost(self):
        statement = replace(self.statement, claimed_cost=1)
        self.assertFalse(self.verify(statement=statement).cost_integrity)

    def test_goal_6_rejects_cost_above_threshold(self):
        statement = replace(self.statement, threshold=1)
        self.assertFalse(self.verify(statement=statement).threshold)


if __name__ == "__main__":
    unittest.main()
