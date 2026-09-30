"""Rebuild legacy exports in a NEW directory, preserving trace salts/alignment.

Does not validate the legacy hash chain and does not authenticate its source.
Use only a trusted source snapshot. Reapprove the MiMC snapshot and new audit
manifest independently. Legacy files are never modified or deleted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from zkalign.append_log import AppendOnlyTraceLog
from zkalign.mimc import HASH_SCHEME, file_mimc


def migrate(source: Path, destination: Path, dataset: Path | None = None) -> None:
    if destination.exists():
        raise ValueError("destination must be a new directory")
    rows = [json.loads(line) for line in (source / "commitment_log/private_trace_records.jsonl").read_text().splitlines() if line.strip()]
    # Validate the entire roster before creating anything. Never renumber cases.
    if not rows or [row["index"] for row in rows] != list(range(len(rows))):
        raise ValueError("source must contain contiguous indices from zero")
    if len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("source contains duplicate case IDs")
    destination.mkdir(parents=True, mode=0o700)
    log = AppendOnlyTraceLog(destination / "commitment_log")
    for row in rows:
        log.append(row["case_id"], row["activity_ids"], salt=bytes.fromhex(row["salt"]))
        if (row["index"] + 1) % 100 == 0:
            print(f"Rebuilt {row['index'] + 1}/{len(rows)} MiMC records", flush=True)
    validation = log.verify_complete_history()
    # Native Go independently rebuilds the circuit root and every commitment.
    reference = json.loads(subprocess.check_output([
        "go", "run", "./cmd/zkalign-hash", "-records",
        str((destination / "commitment_log/private_trace_records.jsonl").resolve()),
    ], cwd=ROOT, text=True))
    if int(log.tree.root().hex(), 16) != int(reference["root"]):
        raise ValueError("Python/Go MiMC root mismatch")
    for record, entry in zip(log.records, reference["cases"], strict=True):
        if record.index != entry["index"] or int(record.commitment, 16) != int(entry["commitment"]):
            raise ValueError("Python/Go commitment mismatch")

    # Copy only named model/analysis artifacts. Old proofs and audit manifests
    # have old fingerprints and must not be carried into a new audit implicitly.
    for name in ("alignment_summary.csv", "circuit_model.json", "sepsis_model.pnml", "sepsis_model.svg", "split_manifest.json"):
        if (source / name).exists(): shutil.copy2(source / name, destination / name)
    path = source / "alignment_witnesses.json"
    if path.exists():
        witnesses = json.loads(path.read_text())
        for witness in witnesses:
            record = log.records[witness["trace_index"]]
            if record.case_id != witness["case_id"] or list(record.activity_ids) != witness["private_trace_activity_ids"] or record.salt != witness["private_trace_salt"]:
                raise ValueError("witness differs from source record")
            witness.update(schema="zkalign.pm4py-witness.v2", hash_scheme=HASH_SCHEME,
                           trace_commitment=record.commitment, public_log_root=log.tree.root().hex(),
                           private_sparse_merkle_proof=log.proof_for_index(record.index).to_dict())
        (destination / path.name).write_text(json.dumps(witnesses, indent=2))
    path = source / "alignment_coverage.json"
    if path.exists():
        coverage = json.loads(path.read_text())
        coverage.update(source_log_root=log.tree.root().hex(), hash_scheme=HASH_SCHEME)
        (destination / path.name).write_text(json.dumps(coverage, indent=2))
    path = source / "run_metadata.json"
    if path.exists():
        metadata = json.loads(path.read_text())
        for key in list(metadata):
            if key.endswith("_sha256"): del metadata[key]
        metadata["hash_scheme"] = HASH_SCHEME
        metadata["append_only_log"].update(merkle_root=log.tree.root().hex(),
            checkpoint_chain_head=log.checkpoints[-1]["checkpoint_hash"], history_validation=validation)
        if dataset is not None: metadata["source_log_mimc"] = file_mimc(dataset)
        if (destination / "sepsis_model.pnml").exists(): metadata["model_pnml_mimc"] = file_mimc(destination / "sepsis_model.pnml")
        (destination / path.name).write_text(json.dumps(metadata, indent=2))
    print(f"Migrated {len(rows)} records; every Python/Go commitment and the final root match.")
    print(f"MiMC root (hex): {log.tree.root().hex()}")
    print("Legacy source unchanged. Create a NEW audit and independently approve its manifest.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--dataset", type=Path)
    args = parser.parse_args()
    migrate(args.source, args.destination, args.dataset)
