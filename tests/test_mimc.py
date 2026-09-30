import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from zkalign.append_log import AppendOnlyTraceLog
from zkalign.mimc import file_mimc, mimc_bytes
from zkalign.mimc_constants import ROUND_CONSTANTS

ROOT = Path(__file__).resolve().parents[1]


class MiMCCompatibilityTests(unittest.TestCase):
    def reference(self, *args):
        return subprocess.check_output(["go", "run", "./cmd/zkalign-hash", *args], cwd=ROOT, text=True).strip()

    def test_constants_match_pinned_gnark(self):
        self.assertEqual(list(ROUND_CONSTANTS), json.loads(self.reference("-constants")))

    def test_byte_framing(self):
        parts = [(), (b"",), (b"\x00",), (b"\x00\x00",), (b"\x01",),
                 (b"\x00\x01",), (b"\x01\x00",), (b"a", b"b"), (b"ab",)]
        self.assertEqual(len(parts), len({mimc_bytes(*items) for items in parts}))

    def test_file_fingerprint_matches_go(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bytes.bin"
            # Includes high bytes, chunk boundaries and leading/trailing zeroes.
            for value in (b"", bytes(range(256)) + bytes(32)):
                path.write_bytes(value)
                self.assertEqual(file_mimc(path), self.reference("-file", str(path)))

    def test_trace_commitments_and_root_match_go(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AppendOnlyTraceLog(directory)
            log.append("a", [5, 4, 6, 10, 3], salt=bytes(32))
            log.append("b", [1, 16, 1], salt=b"\xff" * 32)
            log.append("c", [2] * 185, salt=(42).to_bytes(32, "big"))
            reference = json.loads(self.reference("-records", str(log.records_path)))
            self.assertEqual(int.from_bytes(log.tree.root(), "big"), int(reference["root"]))
            for record, entry in zip(log.records, reference["cases"], strict=True):
                self.assertEqual(record.index, entry["index"])
                self.assertEqual(int(record.commitment, 16), int(entry["commitment"]))

    def test_legacy_store_is_not_silently_reinterpreted(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AppendOnlyTraceLog(directory)
            log.append("a", [1])
            record = json.loads(log.records_path.read_text())
            del record["hash_scheme"]
            log.records_path.write_text(json.dumps(record) + "\n")
            with self.assertRaisesRegex(ValueError, "legacy hash scheme"):
                AppendOnlyTraceLog(directory)

    def test_case_identifier_tampering_changes_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AppendOnlyTraceLog(directory)
            log.append("a", [1])
            record = json.loads(log.records_path.read_text())
            record["case_id"] = "changed"
            log.records_path.write_text(json.dumps(record) + "\n")
            with self.assertRaisesRegex(ValueError, "checkpoint mismatch"):
                AppendOnlyTraceLog(directory)
