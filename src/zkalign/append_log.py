from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .sparse_merkle import SparseMerkleProof, SparseMerkleTree, sha256

TRACE_DOMAIN = b"zkALIGN:committed-trace:v1"
CHECKPOINT_DOMAIN = b"zkALIGN:append-checkpoint:v1"
GENESIS_CHAIN_HASH = bytes(32)


def canonical_trace_encoding(
    index: int, case_id: str, activity_ids: list[int]
) -> bytes:
    case_bytes = case_id.encode("utf-8")
    if index < 0 or len(case_bytes) > 65535:
        raise ValueError("invalid trace index or case identifier")
    if not activity_ids or any(not 0 < activity <= 0xFFFFFFFF for activity in activity_ids):
        raise ValueError("a trace must contain non-zero 32-bit activity IDs")
    return b"".join(
        (
            TRACE_DOMAIN,
            struct.pack(">Q", index),
            struct.pack(">H", len(case_bytes)),
            case_bytes,
            struct.pack(">I", len(activity_ids)),
            *(struct.pack(">I", activity) for activity in activity_ids),
        )
    )


def trace_commitment(
    index: int, case_id: str, activity_ids: list[int], salt: bytes
) -> bytes:
    if len(salt) != 32:
        raise ValueError("trace salts must be 32 bytes")
    return sha256(canonical_trace_encoding(index, case_id, activity_ids), salt)


def derive_trace_salt(master_secret: bytes, index: int, case_id: str) -> bytes:
    if len(master_secret) < 32:
        raise ValueError("master secret must contain at least 256 bits")
    return hmac.new(
        master_secret,
        TRACE_DOMAIN + struct.pack(">Q", index) + case_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()


@dataclass(frozen=True)
class TraceRecord:
    index: int
    case_id: str
    activity_ids: tuple[int, ...]
    salt: str
    commitment: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "case_id": self.case_id,
            "activity_ids": list(self.activity_ids),
            "salt": self.salt,
            "commitment": self.commitment,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "TraceRecord":
        return cls(
            index=int(raw["index"]),
            case_id=str(raw["case_id"]),
            activity_ids=tuple(int(item) for item in raw["activity_ids"]),
            salt=str(raw["salt"]),
            commitment=str(raw["commitment"]),
        )


class AppendOnlyTraceLog:
    """Hash-chained append-only trace records backed by one sparse Merkle tree.

    The files are a local prototype. To prevent a log owner from replacing the
    entire history, public checkpoint roots must later be signed/timestamped or
    anchored in an external append-only service.
    """

    def __init__(self, directory: str | Path, depth: int = 32) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.records_path = self.directory / "private_trace_records.jsonl"
        self.checkpoints_path = self.directory / "checkpoints.jsonl"
        self.secret_path = self.directory / "commitment_master_secret.key"
        self.public_checkpoint_path = self.directory / "public_checkpoint.json"
        self.tree = SparseMerkleTree(depth)
        self.records: list[TraceRecord] = []
        self.checkpoints: list[dict[str, object]] = []
        self._load_and_verify()

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        rows = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from error
        return rows

    @staticmethod
    def checkpoint_hash(
        previous: bytes, index: int, leaf_count: int, commitment: bytes, root: bytes
    ) -> bytes:
        return sha256(
            CHECKPOINT_DOMAIN,
            previous,
            struct.pack(">Q", index),
            struct.pack(">Q", leaf_count),
            commitment,
            root,
        )

    def _load_and_verify(self) -> None:
        raw_records = self._read_jsonl(self.records_path)
        raw_checkpoints = self._read_jsonl(self.checkpoints_path)
        if len(raw_records) != len(raw_checkpoints):
            raise ValueError("record/checkpoint counts differ; append history is incomplete")
        previous = GENESIS_CHAIN_HASH
        for expected_index, (raw_record, checkpoint) in enumerate(
            zip(raw_records, raw_checkpoints, strict=True)
        ):
            record = TraceRecord.from_dict(raw_record)
            if record.index != expected_index:
                raise ValueError("trace indices are not contiguous from zero")
            salt = bytes.fromhex(record.salt)
            commitment = trace_commitment(
                record.index, record.case_id, list(record.activity_ids), salt
            )
            if commitment.hex() != record.commitment:
                raise ValueError(f"trace commitment mismatch at index {record.index}")
            root = self.tree.insert(record.index, commitment)
            expected_chain = self.checkpoint_hash(
                previous, record.index, record.index + 1, commitment, root
            )
            if (
                int(checkpoint.get("index", -1)) != record.index
                or int(checkpoint.get("leaf_count", -1)) != record.index + 1
                or checkpoint.get("previous_checkpoint_hash") != previous.hex()
                or checkpoint.get("trace_commitment") != commitment.hex()
                or checkpoint.get("merkle_root") != root.hex()
                or checkpoint.get("checkpoint_hash") != expected_chain.hex()
            ):
                raise ValueError(f"append checkpoint mismatch at index {record.index}")
            self.records.append(record)
            self.checkpoints.append(checkpoint)
            previous = expected_chain

    def master_secret(self) -> bytes:
        if not self.secret_path.exists():
            self.secret_path.write_bytes(os.urandom(32))
            self.secret_path.chmod(0o600)
        secret = self.secret_path.read_bytes()
        if len(secret) != 32:
            raise ValueError("invalid commitment master secret")
        return secret

    def append(self, case_id: str, activity_ids: list[int]) -> TraceRecord:
        if any(record.case_id == case_id for record in self.records):
            raise ValueError(f"case {case_id!r} was already appended")
        index = len(self.records)
        salt = derive_trace_salt(self.master_secret(), index, case_id)
        commitment = trace_commitment(index, case_id, activity_ids, salt)
        root = self.tree.insert(index, commitment)
        previous = (
            bytes.fromhex(str(self.checkpoints[-1]["checkpoint_hash"]))
            if self.checkpoints
            else GENESIS_CHAIN_HASH
        )
        chain_hash = self.checkpoint_hash(
            previous, index, index + 1, commitment, root
        )
        record = TraceRecord(index, case_id, tuple(activity_ids), salt.hex(), commitment.hex())
        checkpoint: dict[str, object] = {
            "index": index,
            "leaf_count": index + 1,
            "previous_checkpoint_hash": previous.hex(),
            "trace_commitment": commitment.hex(),
            "merkle_root": root.hex(),
            "checkpoint_hash": chain_hash.hex(),
        }
        with self.records_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record.to_dict(), separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        with self.checkpoints_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(checkpoint, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.records.append(record)
        self.checkpoints.append(checkpoint)
        self.write_public_checkpoint()
        return record

    def append_many(self, traces: Iterable[tuple[str, list[int]]]) -> None:
        existing = {record.case_id: record for record in self.records}
        for case_id, activities in traces:
            if case_id in existing:
                record = existing[case_id]
                expected = trace_commitment(
                    record.index,
                    case_id,
                    activities,
                    bytes.fromhex(record.salt),
                ).hex()
                if expected != record.commitment:
                    raise ValueError(f"existing case {case_id!r} has different contents")
                continue
            record = self.append(case_id, activities)
            existing[case_id] = record

    def write_public_checkpoint(self) -> dict[str, object]:
        checkpoint = {
            "schema": "zkalign.public-log-checkpoint.v1",
            "tree_depth": self.tree.depth,
            "leaf_count": len(self.records),
            "first_index": 0 if self.records else None,
            "last_index": len(self.records) - 1 if self.records else None,
            "merkle_root": self.tree.root().hex(),
            "checkpoint_chain_head": (
                self.checkpoints[-1]["checkpoint_hash"]
                if self.checkpoints
                else GENESIS_CHAIN_HASH.hex()
            ),
            "coverage_rule": "exact contiguous indices [0, leaf_count)",
        }
        self.public_checkpoint_path.write_text(
            json.dumps(checkpoint, indent=2), encoding="utf-8"
        )
        return checkpoint

    def proof_for_index(self, index: int) -> SparseMerkleProof:
        if not 0 <= index < len(self.records):
            raise IndexError(index)
        return self.tree.proof(index)

    def verify_membership(self, record: TraceRecord, proof: SparseMerkleProof) -> bool:
        return self.tree.verify(
            bytes.fromhex(record.commitment), proof, self.tree.root()
        )

    def verify_complete_history(self) -> dict[str, object]:
        reloaded = AppendOnlyTraceLog(self.directory, self.tree.depth)
        proofs_valid = all(
            reloaded.verify_membership(record, reloaded.proof_for_index(record.index))
            for record in reloaded.records
        )
        return {
            "records": len(reloaded.records),
            "contiguous_indices": [record.index for record in reloaded.records]
            == list(range(len(reloaded.records))),
            "checkpoint_chain_valid": len(reloaded.records) == len(reloaded.checkpoints),
            "all_membership_proofs_valid": proofs_valid,
            "merkle_root": reloaded.tree.root().hex(),
        }
