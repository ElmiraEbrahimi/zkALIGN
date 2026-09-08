from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from zkalign.append_log import AppendOnlyTraceLog
from zkalign.sparse_merkle import SparseMerkleTree, sha256


class SparseMerkleTreeTests(unittest.TestCase):
    def test_membership_and_non_membership(self):
        tree = SparseMerkleTree(depth=8)
        value = sha256(b"trace-commitment")
        tree.insert(7, value)
        self.assertTrue(tree.verify(value, tree.proof(7), tree.root()))
        self.assertTrue(tree.verify(None, tree.proof(8), tree.root()))

    def test_wrong_value_and_wrong_root_are_rejected(self):
        tree = SparseMerkleTree(depth=8)
        value = sha256(b"trace-commitment")
        tree.insert(7, value)
        proof = tree.proof(7)
        self.assertFalse(tree.verify(sha256(b"changed"), proof, tree.root()))
        self.assertFalse(tree.verify(value, proof, sha256(b"wrong-root")))

    def test_existing_leaf_cannot_be_overwritten(self):
        tree = SparseMerkleTree(depth=8)
        tree.insert(1, sha256(b"first"))
        with self.assertRaises(ValueError):
            tree.insert(1, sha256(b"replacement"))


class AppendOnlyTraceLogTests(unittest.TestCase):
    def test_append_reload_and_complete_history_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AppendOnlyTraceLog(directory, depth=8)
            log.append_many([("patient-a", [1, 2, 3]), ("patient-b", [1, 4, 3])])
            validation = log.verify_complete_history()
            self.assertEqual(2, validation["records"])
            self.assertTrue(validation["contiguous_indices"])
            self.assertTrue(validation["checkpoint_chain_valid"])
            self.assertTrue(validation["all_membership_proofs_valid"])

            reloaded = AppendOnlyTraceLog(directory, depth=8)
            self.assertEqual(log.tree.root(), reloaded.tree.root())

    def test_same_case_is_idempotent_but_changed_case_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AppendOnlyTraceLog(directory, depth=8)
            log.append_many([("patient-a", [1, 2, 3])])
            log.append_many([("patient-a", [1, 2, 3])])
            self.assertEqual(1, len(log.records))
            with self.assertRaises(ValueError):
                log.append_many([("patient-a", [1, 9, 3])])

    def test_checkpoint_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AppendOnlyTraceLog(directory, depth=8)
            log.append("patient-a", [1, 2, 3])
            checkpoint_path = Path(directory) / "checkpoints.jsonl"
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint["merkle_root"] = "00" * 32
            checkpoint_path.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                AppendOnlyTraceLog(directory, depth=8)


if __name__ == "__main__":
    unittest.main()
