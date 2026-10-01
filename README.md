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
- Private exact-cost recomputation and a public threshold check. The exact
  cost is not a public input or part of an auditor proof bundle.
- Negative tests for trace substitution, fake moves, incomplete alignments,
  incorrect cost, and threshold failure.
- A Go/gnark circuit for one real held-out Sepsis trace against the fixed real
  27-place, 35-transition Petri net.
- A circuit-compatible MiMC trace commitment and 32-level sparse-Merkle
  membership check over all 1,050 committed traces.
- A real Groth16 setup, proof generator, verifier, proof artifact, positive
  tests, and negative tests for each security boundary.
- An external population auditor that verifies separate single-trace proofs
  against a pinned snapshot, population, key and threshold, rejects duplicate
  counting, and reports a certified lower bound against a percentage target.
  This does not introduce batching or recursion into the circuit.

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
PROOF VERIFIED SUCCESSFULLY: the committed trace admits a valid, complete alignment with cost <= 1. The exact cost remains private.
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

### Certify a percentage with separate single-trace proofs

**Private-cost format change:** audit version
`zkalign-single-trace-audit-v3-mimc-private-cost` has exactly three public
circuit fields: commitment, root and threshold. The claimed exact cost is a
private witness constrained to the move-derived cost. Regenerate setup keys,
manifests and proofs in a **new directory** with `init` and `prove`; existing
public-cost (v2) artifacts are not compatible and are rejected. Old files are
not deleted or made private retroactively. Already disclosed costs cannot be
hidden by generating a new proof.

The new `zkalign-audit` command fixes a population **before** proving. It uses
one shared Groth16 setup for all proofs. The independent verifier counts only
distinct approved commitments with valid proofs. Its denominator is always
the full agreed population, not the number of proof files supplied.

Run this small real-data demonstration from the repository root. Use a new
output directory for each audit configuration. Existing audit artifacts are
never silently overwritten.

```bash
go run ./cmd/zkalign-audit init \
  -out outputs/sepsis/audit-demo \
  -cases A,AB,AG -threshold 1 -target 95

go run ./cmd/zkalign-audit prove -audit outputs/sepsis/audit-demo
```

The three demonstration cases have candidate costs 0, 0 and 1. This is an
explicit **three-case demonstration scope**, not evidence about all 1,050
cases. The circuit's 64-move limit remains unchanged. A missing alignment,
capacity failure, invalid witness or candidate cost above K leaves that case
uncertified and does not reduce the denominator. The prover reports such
cases and continues. Re-running `prove` preserves existing proof files.

The `init` command prints a domain-separated MiMC manifest fingerprint. Before accepting
proofs, the auditor must approve the scope, authentic snapshot, model/circuit,
setup/key and policy, then retain that fingerprint independently. Replace the
placeholder below with **that retained fingerprint**. Do not derive the pin
from an untrusted manifest received alongside the proofs.

```bash
go run ./cmd/zkalign-audit verify \
  -manifest outputs/sepsis/audit-demo/manifest.json \
  -pin YOUR_PREVIOUSLY_APPROVED_MANIFEST_MIMC \
  -vk outputs/sepsis/audit-demo/verification.key \
  -proofs outputs/sepsis/audit-demo/proofs \
  -report outputs/sepsis/audit-demo/verified-report.json
```

Expected result for the demonstration is:

```text
CERTIFIED: 3/3 agreed traces (100.00%). Required: 3 for target 95% at K=1.
UNCERTIFIED: 0. Missing/invalid proofs do not establish nonconformance.
AUDIT TARGET MET: at least 95% of the agreed traces admit a valid, complete alignment with cost <= 1.
```

The verifier reads only the manifest, verification key and proof bundles. It
can run in a separate directory or machine without event logs, alignments,
salts or the proving key. It verifies every bundle against the same approved
root, threshold and key. Copying a proof file does not increase the numerator.
Invalid files are recorded in the report but cannot certify a case. An invalid
attempt does not prevent a later valid proof from certifying the same case.
For 100 agreed cases, 95 distinct valid proofs suffice for the 95% lower-bound
claim. The decision uses exact integer arithmetic, not the rounded percentage
printed on the console. Exit status is 0 when the target is established, 2
when it is not established, and 1 for configuration or I/O errors. When using
`go run`, Go may wrap the program's nonzero exit status. Use a compiled binary
if another program needs to distinguish exit statuses.

Omit `-cases` during `init` to fix **all stored cases** as the population.
Do not do this expecting the current saved witnesses to cover all 1,050 cases
because the pipeline aligns only the 210 held-out cases. The remaining cases
will be uncertified. To audit a larger agreed scope, first prepare its candidate
alignments without silently excluding difficult cases. The existing move bound
can also prevent certification. None of these failures proves nonconformance.

Audit artifacts are generated under ignored `outputs/`:

| Artifact | Purpose | Share with auditor? |
| --- | --- | --- |
| `manifest.json` | Agreed root, K, target, key fingerprint and population commitments/indices | Yes, for approval |
| `manifest.mimc` | Convenience copy of the proposed MiMC fingerprint | Not a substitute for an independently retained pin |
| `verification.key` | Shared, approved Groth16 verification key | Yes |
| `proving.key` | Shared proving material | Not needed by the auditor |
| `proofs/trace-INDEX.json` | One proof, public commitment and manifest fingerprint; no exact cost | Yes |
| `verified-report.json` | Verifier's counts, case indices and per-file decisions | Auditor output |

Public indices and commitments are linkable audit metadata. The threshold and
certification status are also public, but the exact alignment cost is private.
No patient identifiers, trace activities, salts, alignment arrays or exact
costs are written to these public bundles. Proof acceptance still reveals that
some valid alignment has cost at most K (so K=0 implies cost zero). Repeated
audits under different thresholds can reveal further bounds. A verifier must trust the approved roster to associate
each commitment with a distinct intended real-world case. The circuit proves
membership of the commitment, not authenticity of a patient record or the
external roster. Root publication and approval remain organizational steps,
and the local Groth16 setup is not a multiparty ceremony. Do not trust a setup
performed solely by a potentially malicious prover. The Python append store
and the circuit now use the same MiMC trace commitments and Merkle root. The
local checkpoint chain is also MiMC, but append-only evolution and event
authenticity are still not proven by the single-trace circuit.

The result is an externally verified **lower bound**, not one aggregate ZK
proof, exact optimal fitness, a whole-log completeness proof, or proof that
uncertified cases violate the threshold. No batching or recursion is used.
Implementation is in `circuit/audit.go` and `cmd/zkalign-audit/main.go`.

### Run every test

```bash
make test
```

The Python commitment tests should end with `OK`; the Go output should contain
`ok github.com/ElmiraEbrahimi/zkALIGN/circuit`. The Go tests include real
Groth16 proofs plus rejection tests for changed trace data, wrong Merkle paths,
trace/alignment mismatches, illegal Petri-net transitions, incomplete
alignments, false costs, and thresholds that are too low. Audit tests also cover
proof serialization, missing cases, duplicates, wrong roots/thresholds/keys,
changed manifests, unexpected commitments and exact percentage boundaries.

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

The Python append log and gnark proof layer use identical BN254 MiMC trace
commitments, indexed leaves, level-separated internal nodes and empty nodes.
They derive the same root from the same 1,050 private trace records. The proof
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
Groth16 proof + public root/commitment/threshold (exact cost private)
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

## MiMC hash format and legacy migration

All application-level hashing uses BN254 MiMC matching gnark-crypto v0.21.0.
This includes trace commitments, Merkle nodes, append checkpoints, manifest
and verification-key fingerprints, dataset checksums and model-file checksums.
`hashing/mimc.go` and `src/zkalign/mimc.py` define the matching encodings.
Python's fixed round constants are checked against the pinned Go library.
The Python tree root is hexadecimal while the audit manifest's root is decimal
because gnark uses field values. These are different representations of the
same number, not different roots.

Arbitrary byte strings use domain-separated, length-prefixed parts and 31-byte
chunks. This avoids lossy reduction of file bytes modulo the field. Trace
encoding remains the circuit's domain, length, 185 padded activity IDs and
salt reduced into the field. New traces use independent OS-random 32-byte salts
instead of the previous hash-based salt derivation. The local checkpoint also
binds the case ID, which is not part of the circuit's trace payload.

This is a versioned migration. Old SHA-based checkpoints and audit manifests
are rejected, not silently treated as MiMC. To rebuild a trusted legacy export
without recomputing alignments or deleting its original files:

```bash
.venv/bin/python scripts/migrate_mimc.py \
  --source outputs/sepsis \
  --destination outputs/sepsis-mimc \
  --dataset 'datasets/raw/Sepsis Cases - Event Log.xes.gz'
```

The destination must not exist. Migration preserves trace indices, activities,
salts and candidate alignments and cross-checks **every commitment and the root**
against Go. It does not authenticate the legacy input or validate its old hash
chain. Obtain that source from a trusted snapshot. Old proof packages and audit
manifests are not copied. Create and approve a fresh MiMC audit using `init` and
pass the migrated `-records` path, then use `prove` with both migrated `-records`
and `-witnesses` paths. Once independently checked, the migrated directory can
replace the working export while retaining the old directory as a backup.

Third-party cryptographic internals are not rewritten. In particular, gnark's
MiMC parameter derivation and proof-system internals retain their standard
library implementations. “MiMC-only” here describes zkALIGN's application
hashes, not every primitive used internally by its dependencies or TLS.

## Important claim boundary

The base circuit proves that **a valid, complete alignment with the verified
cost exists**. It does not prove that the supplied alignment is globally
optimal. PM4Py/A* can find an optimal candidate outside the circuit, but the
base circuit does not prove that A* was run correctly. Global optimality needs a
separate zkVM execution proof or shortest-path optimality certificate.
