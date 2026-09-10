# zkALIGN

Research prototype for zero-knowledge verification of alignment-based
conformance checking.

The central design rule is:

> Find a candidate alignment outside the ZK circuit; verify its validity,
> completeness, cost, commitment, and threshold inside the circuit.

The implementation uses the public Sepsis Cases hospital event log and a real
discovered Petri net with branches, loops, parallel behavior, and silent
transitions. The former linear teaching circuit has been replaced by
`SingleTracePetriNetCircuit`.

## What is implemented

- PM4Py state-equation A* alignment generation outside the circuit.
- Canonical commitments with domain separation, length, padding, and salt.
- Exact-cost and threshold checks.
- Negative tests for trace substitution, fake moves, incomplete alignments,
  incorrect cost, and threshold failure.
- A Go/gnark circuit for one real held-out Sepsis trace against the fixed real
  27-place, 35-transition Petri net.
- A circuit-compatible MiMC trace commitment and 32-level sparse-Merkle
  membership check over all 1,050 committed traces.
- A real Groth16 setup, proof generator, verifier, proof artifact, positive
  tests, and negative tests for each security boundary.

## Quick start

### First-time setup

From a terminal opened in the repository:

```bash
cd "/Users/elmiraebrahimi/Documents/proccess mining-m1/zkALIGN"
make setup
make pre-zkp
```

`make pre-zkp` downloads and checksum-verifies the Sepsis log, discovers the
model, aligns all held-out cases, and prepares the ignored private witness
files. These two commands are needed only on a new checkout or when regenerating
the experiment.

### Generate and verify one real proof

```bash
make prove
```

The default invocation proves held-out case `AG` with public cost threshold 1.
Expected important output:

```text
Preparing real Sepsis case AG (trace index 13): 5 events, 18 alignment moves.
Compiled SingleTracePetriNetCircuit with 137925 constraints.
PROOF VERIFIED SUCCESSFULLY: case AG has a valid, complete alignment with cost 1, which is within threshold 1.
Proof written to outputs/sepsis/proofs/single_trace.groth16.
```

Exact timings can differ by computer. Select another case or threshold with:

```bash
go run ./cmd/zkalign-proof -case AG -threshold 1
```

The selected case must fit the current bounds of 185 trace events and 64
alignment moves. To see an intentional threshold rejection:

```bash
go run ./cmd/zkalign-proof -case AG -threshold 0
```

Case `AG` has verified cost 1, so threshold 0 must fail. This failure is
expected and demonstrates Goal 6.

### Run every test

```bash
make test
```

The Python commitment tests should end with `OK`; the Go output should contain
`ok github.com/ElmiraEbrahimi/zkALIGN/circuit`. The Go tests include one real
Groth16 proof plus rejection tests for changed trace data, wrong Merkle paths,
trace/alignment mismatches, illegal Petri-net transitions, incomplete
alignments, false costs, and thresholds that are too low.

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

Generate and verify a proof for real held-out case `AG` (unit alignment cost 1):

```bash
make prove
```

The command reads the PM4Py witness and private commitment records, compiles
the fixed real Petri net into the gnark constraints, generates a Groth16 proof,
verifies it using only the proof and public witness, and writes the ignored
proof artifact to `outputs/sepsis/proofs/single_trace.groth16`. A successful run
ends with:

```text
PROOF VERIFIED SUCCESSFULLY: case AG has a valid, complete alignment with cost 1, which is within threshold 1.
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

The existing auditable Python append log continues to use SHA-256. The gnark
proof layer deterministically derives a separate MiMC commitment tree from the
same 1,050 private trace records because MiMC is circuit-friendly. The proof
binds the private trace to this MiMC root; production deployment must publish
or anchor that public root alongside the existing audit checkpoint.

## Architecture

```text
private trace + fixed real Sepsis Petri net
          |
          v
off-circuit PM4Py state-equation A* alignment
          |
          v
real PM4Py witness + MiMC event-log membership path
          |
          v
six checks in SingleTracePetriNetCircuit
          |
          v
Groth16 proof + public root/commitment/cost/threshold
```

The current circuit bound is 185 trace events and 64 alignment moves. It proves
one trace at a time. Case `AG` uses 5 events and 18 moves. Increasing the move
bound to the dataset maximum and recursive batch aggregation are later measured
optimization stages, not claims made by this implementation.

See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for the staged
research plan and the exact role PM4Py should play.

For a group-readable explanation of Petri-net choices, parallelism, loops,
numeric encodings, circuit inputs, data structures, every constraint group, and
security limitations, read
[`docs/CIRCUIT_IMPLEMENTATION_GUIDE.md`](docs/CIRCUIT_IMPLEMENTATION_GUIDE.md).

## Important claim boundary

The base circuit proves that **a valid, complete alignment with the verified
cost exists**. It does not prove that the supplied alignment is globally
optimal. PM4Py/A* can find an optimal candidate outside the circuit, but the
base circuit does not prove that A* was run correctly. Global optimality needs a
separate zkVM execution proof or shortest-path optimality certificate.
