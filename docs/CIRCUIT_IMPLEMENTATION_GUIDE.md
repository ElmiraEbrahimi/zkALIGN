# zkALIGN circuit implementation guide

This guide explains what the implementation proves, how the real Sepsis Petri
net becomes gnark constraints, and where each part lives. Start here before
changing the circuit.

## End-to-end data flow

```text
Sepsis event log: 1,050 patient traces
                    |
                    +--> 840 training traces
                    |          |
                    |     Inductive Miner
                    |          |
                    |     Petri net model
                    |     27 places, 35 transitions, 82 arcs
                    |
                    +--> 210 held-out traces
                               |
                 PM4Py state-equation A* + Petri net
                               |
                    candidate alignment per trace
                               |
                  Go witness adapter for one trace
                               |
                 SingleTracePetriNetCircuit (gnark)
                               |
                      Groth16 proof + verifier
```

PM4Py searches for the candidate alignment outside the circuit. The circuit
does not repeat A* search; it checks that the supplied alignment is legal,
complete, correctly priced, and bound to committed data.

## Petri-net vocabulary

- **Place:** a circle that can hold a token. It represents a process condition.
- **Transition:** a box that consumes tokens from input places and creates
  tokens in output places. A visible transition has one of the 16 healthcare
  activity labels. A silent transition has label `0` and performs only internal
  routing.
- **Arc:** an arrow connecting a place and transition.
- **Marking:** the token count for all 27 places; it is the complete model state.

The current model is one-safe, so every marking entry is constrained to `0` or
`1`. More than one entry may be `1` at the same time when parallel paths are
active.

### Sequence

```text
(P1) -> [ER Registration] -> (P2)
```

The transition removes the token from `P1` and creates one in `P2`.

### Choice (XOR branch)

```text
          -> [Release] -> (P2)
(P1) ----|
          -> [Admit]   -> (P3)
```

Both transitions need the same token from `P1`. Firing either transition
removes it, so only one choice can be taken.

### Parallel split and join

```text
                    -> (P2: test A active)
(P1) -> [split] ---|
                    -> (P3: test B active)

(P2) ---|
         -> [join] -> (P4)
(P3) ---|
```

The split produces two tokens. The join requires both tokens. The circuit does
not need a special "parallel" instruction; the marking and transition arcs
naturally enforce it.

### Loop

```text
(P1) -> [Examine] -> (P2) -> [Repeat] -> (P1)
```

The `Repeat` transition sends the token back to an earlier place. Repetition is
legal only when the fixed Petri net contains such a path.

## Numeric encodings

The private trace contains activity IDs, not strings:

```text
Admission IC=1, Admission NC=2, CRP=3, ER Registration=4,
ER Sepsis Triage=5, ER Triage=6, IV Antibiotics=7, IV Liquid=8,
LacticAcid=9, Leucocytes=10, Release A=11, Release B=12,
Release C=13, Release D=14, Release E=15, Return ER=16
```

There are 35 transition IDs because the Petri net also contains 21 silent
transitions. A trace event stores an activity ID `1..16`; a model-consuming
alignment move selects a transition ID `1..35`. For a synchronous move, the
circuit requires the selected transition's label ID to equal the trace activity
ID.

Move encoding:

```text
0 = PAD    unused fixed-array position
1 = SYNC   trace and model perform the same visible activity
2 = LOG    trace activity occurs without a model transition
3 = MODEL  model transition occurs without consuming a trace event
```

## Model data structure

The model is a graph in PM4Py. `scripts/generate_gnark_model.py` converts that
graph into fixed sparse Go constants in `circuit/sepsis_model_gen.go`.

The circuit stores, conceptually:

```text
initial marking[27]
final marking[27]
transition labels[35]
model-move costs[35]
input transitions connected to each place
output transitions connected to each place
```

Sparse incidence lists are used because the model has only 82 real arcs. Dense
input/output matrices would hold `35 * 27 * 2 = 1,890` entries, most of them
zero. For each selected transition and place, the circuit calculates:

```text
next_marking[p] = marking[p] - selected_input[p] + selected_output[p]
```

It first proves that every required input place contains a token and then proves
that the resulting one-safe marking remains Boolean.

The model constants are compiled into the constraint system; they are not sent
as hundreds of public inputs for every proof. A changed model requires regenerated
constants and new circuit/proving/verifying keys.

## Circuit inputs

Public inputs, visible to the verifier:

```text
TraceCommitment  salted commitment to the private padded trace
EventLogRoot     MiMC sparse-Merkle root for all 1,050 committed traces
CostThreshold    maximum cost accepted by the verifier
AlignmentCost    cost that the circuit must independently reproduce
```

Private witness values:

```text
TraceLength, TraceEvents[185], TraceSalt, TraceIndex, MerklePath[32]
AlignmentLength, move types[64], activities[64], transition IDs[64]
```

Arrays have fixed circuit bounds. Real values occupy a prefix, followed by
canonical zero padding. The current 64-move alignment bound includes the real
default case `AG` but does not include every held-out case; increasing and
benchmarking this bound is future scalability work.

## The six circuit checks

1. **Commitment/binding:** recompute the MiMC trace commitment and the 32-level
   Merkle path; require the calculated root to equal public `EventLogRoot`.
2. **Alignment/trace consistency:** each `SYNC` or `LOG` move must consume the
   next private trace event in order.
3. **Move/model legality:** every `SYNC` or `MODEL` move selects a real enabled
   transition; a `SYNC` label must match its trace activity.
4. **Completeness:** every trace event is consumed and the calculated final
   marking equals the fixed accepting marking.
5. **Correct cost:** derive cost from verified moves, never from an untrusted
   witness total.
6. **Threshold:** require calculated cost to be no greater than public `K`.

Cost policy:

```text
SYNC = 0, LOG = 1, silent MODEL = 0, visible MODEL = 1
```

No floating-point numbers are used. IDs, tokens, move types, positions, and
costs are integers represented as BN254 field elements.

## Important files

- `scripts/healthcare_pipeline.py`: real data split, model discovery, A*
  alignment, witness export, and SHA-256 audit commitment log.
- `scripts/generate_gnark_model.py`: converts the exported model into sparse Go
  constants.
- `circuit/sepsis_model_gen.go`: generated fixed real Petri-net constants.
- `circuit/witness.go`: selects one real case and converts PM4Py JSON to a gnark
  assignment; saved pre/post markings are intentionally ignored.
- `circuit/alignment.go`: all six circuit checks.
- `circuit/commitment.go`: host-side MiMC trace commitment matching the circuit.
- `circuit/merkle.go`: builds the MiMC root and membership path from all private
  trace records.
- `circuit/proof.go`: Groth16 proof generator and verifier boundary.
- `cmd/zkalign-proof/main.go`: runnable proof command and human-readable result.
- `circuit/alignment_test.go`: real-model positive proof and adversarial tests.

## Run and interpret the result

From the repository root:

```bash
make prove
```

The default case `AG` has five trace events, eighteen alignment moves, and unit
cost one. Success means the proof verified and cost `1 <= 1`. To demonstrate
threshold rejection, run:

```bash
go run ./cmd/zkalign-proof -case AG -threshold 0
```

That command must fail because the verified cost is one. Run all tests with
`make test`.

## Security and claim boundaries

- The proof establishes existence of a valid complete alignment with the
  verified cost. It does not prove that PM4Py's alignment is globally optimal.
- The SHA-256 append-only audit tree and circuit-friendly MiMC tree are separate
  representations derived from the same private trace records. A production
  deployment must publish or anchor the MiMC root used by the verifier.
- Groth16 keys are tied to the exact circuit bounds and fixed model.
- The current command performs a fresh trusted setup for demonstration. A
  deployment must manage and distribute setup artifacts appropriately.
- The current implementation proves one trace at a time. Batch coverage and
  recursive proof aggregation are later stages.
