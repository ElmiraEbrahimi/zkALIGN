# zkALIGN

Research prototype for zero-knowledge verification of alignment-based
conformance checking.

The central design rule is:

> Find a candidate alignment outside the ZK circuit; verify its validity,
> completeness, cost, commitment, and threshold inside the circuit.

This repository starts with a deliberately small healthcare process represented
as a finite-state machine:

```text
Admit -> Examine -> Approve -> Treat -> Discharge
```

The private example trace is:

```text
Admit -> Examine -> EmergencyTest -> Treat -> Discharge
```

It contains one unexpected event (`EmergencyTest`) and omits `Approve`. With
unit deviation costs, its complete alignment has cost 2.

That linear example is retained only because every circuit constraint can be
checked by hand. It is **not** the main process-mining experiment. The realistic
pipeline uses the public Sepsis Cases hospital event log and a discovered Petri
net with branches, loops, parallel behavior, and silent transitions.

## What is implemented

- A conventional off-circuit shortest-path alignment search in Python.
- A deterministic reference verifier for the six circuit goals.
- Canonical reference commitments with domain separation, length, padding, and salt.
- Exact-cost and threshold checks.
- Negative tests for trace substitution, fake moves, incomplete alignments,
  incorrect cost, and threshold failure.
- A Go/gnark circuit for the same bounded healthcare example, with a real
  Groth16 prove/verify test.

## Quick start

Python 3.11+ is sufficient for the reference prototype:

```bash
python3 -m unittest discover -s tests -v
python3 -m zkalign.cli demo
```

The package lives in `src/`, so when running without installation use:

```bash
PYTHONPATH=src python3 -m zkalign.cli demo
go test ./...
```

## Real healthcare process-mining pipeline

Create a local environment, download the checksum-verified public dataset,
discover the Petri net, and align held-out patient cases:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[process-mining]'
python3 scripts/download_sepsis.py
.venv/bin/python scripts/healthcare_pipeline.py
```

The pipeline:

1. loads 1,050 anonymized sepsis patient pathways (15,214 events);
2. splits whole patient cases into 80% training and 20% held-out data;
3. discovers a sound workflow Petri net with Inductive Miner;
4. aligns all 210 held-out patient cases with PM4Py state-equation A*;
5. exports PNML/SVG, per-case alignment summaries, and private witness records;
6. records each exact Petri-net transition and the marking before/after it;
7. commits all 1,050 traces into one 32-level sparse Merkle tree;
8. maintains a hash-chained append checkpoint for every newly occupied leaf;
9. attaches a 32-sibling Merkle membership proof to every held-out alignment;
10. proves pre-ZKP that the 210 aligned indices cover the held-out partition
    exactly once, without omissions or duplicates.

The current run produced a model with 27 places, 35 transitions, 82 arcs, and
21 silent transitions. All 210 held-out traces completed without timeout or
exclusion: 144 fit the discovered model at unit deviation cost zero and 66 have
at least one deviation. Generated data and witnesses are stored under
`outputs/sepsis/` and ignored by Git because they contain reconstructed event
traces. Dataset provenance and checksum are documented in
[`datasets/README.md`](datasets/README.md).

This is a technical conformance benchmark, not a clinical compliance claim.
The model is learned from hospital behavior; it is not an independently
validated medical guideline. A later clinical study would need a guideline
model reviewed by a healthcare domain expert.

After the one-time environment setup, rerun and test the complete baseline with:

```bash
make pre-zkp
make test
```

## Append-only commitment layer

Each patient trace is canonically encoded using its index, case identifier,
trace length, and integer activity sequence, then salted and hashed. Its
commitment occupies one leaf in a 32-level sparse Merkle tree. Empty leaves have
deterministic default hashes, occupied keys cannot be overwritten, and every
append produces a new root plus a hash-chained checkpoint.

The current public checkpoint binds all 1,050 traces with one Merkle root.
Membership and non-membership proofs are implemented and tested. Reloading the
local history recomputes every trace commitment, tree root, and checkpoint-chain
link; changed records or checkpoints are rejected.

The local files are append-only by application rule, not by physical law. A log
owner with filesystem control could replace the entire directory and recompute
a new history. A production deployment must publish, sign, timestamp, or anchor
checkpoint roots in an independent service. The later ZK circuit verifies
membership against an already-published root; it cannot create provenance by
itself.

Core modules:

- `src/zkalign/sparse_merkle.py`: sparse tree, membership/non-membership proofs.
- `src/zkalign/append_log.py`: salted trace commitments, append checkpoints,
  idempotent ingestion, and complete-history validation.
- `outputs/sepsis/commitment_log/public_checkpoint.json`: public root and chain
  head from the current local run.
- `outputs/sepsis/alignment_coverage.json`: exact held-out coverage manifest.

Private trace records, salts, Merkle paths, and alignment witnesses remain under
the ignored `outputs/` directory and must not be published as public proof
inputs.

The CLI prints the private trace, candidate alignment, commitment, calculated
cost, and the outcome of all six checks. This is a teaching/demo mode; a real
verifier receives only the proof and public inputs.

The readable Python oracle uses SHA-256. The gnark circuit uses MiMC over BN254
field elements because it is circuit-friendly. They intentionally share the
same logical commitment fields but are separate prototype layers; the PM4Py
witness adapter will emit the gnark/MiMC representation used for proofs.

## Architecture

```text
private trace + public model
          |
          v
off-circuit alignment search (Python now; PM4Py adapter later)
          |
          v
canonical private witness
          |
          v
six checks (reference verifier -> gnark circuit)
          |
          v
proof + public commitment/model ID/policy/threshold
```

See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for the staged
research plan and the exact role PM4Py should play.

## Important claim boundary

The base circuit proves that **a valid, complete alignment with the verified
cost exists**. It does not prove that the supplied alignment is globally
optimal. PM4Py/A* can find an optimal candidate outside the circuit, but the
base circuit does not prove that A* was run correctly. Global optimality needs a
separate zkVM execution proof or shortest-path optimality certificate.
