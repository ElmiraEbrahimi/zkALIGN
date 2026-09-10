# zkALIGN implementation plan

## The decision to make first

Do **not** put PM4Py's state-equation A* search inside the first circuit.

Use it outside the circuit to produce a candidate alignment. Convert that
alignment to a fixed witness. The circuit verifies the witness. This follows the
paper's central search-versus-verification separation and gives a prototype that
can realistically be built and tested.

## Healthcare statement

For one private patient episode, the hospital proves:

> I know a trace and complete legal alignment bound to this public commitment;
> the circuit-derived deviation cost is at most the auditor's public threshold.

The implemented public model is the Petri net discovered from the training
partition of the Sepsis Cases event log: 27 places, 35 transitions and 82 arcs.
It is fixed into the gnark constraint system. Real held-out case `AG` is the
default end-to-end proof example.

## The six checks

1. **Binding:** recompute the salted commitment over domain, length, padded
   activity IDs and salt, then prove membership in the public 32-level MiMC
   event-log root.
2. **Trace consistency:** every SYNC/LOG move consumes exactly the next private
   trace event.
3. **Move/model legality:** every SYNC/MODEL move follows an enabled transition;
   SYNC labels must match.
4. **Completeness:** all trace events are consumed and the model ends in an
   accepting state.
5. **Cost:** derive the cost from authenticated move costs rather than trusting
   a witness value.
6. **Threshold:** constrain the derived cost to be at most public `K`.

## Stages

### Stage 1 - real gnark proof (completed for one real trace)

- Fixed capacities of 185 trace events and 64 alignment slots.
- Activity and move types encoded as integers.
- Public real Sepsis Petri net compiled into constraints.
- MiMC commitment in both Go host code and circuit.
- Groth16 compile, setup, prove, and verify test.
- Exact-cost and threshold-only modes.

The command `make prove` performs real Groth16 setup, proving and verification
for held-out case `AG` and writes the proof under ignored generated outputs.

### Stage 2 - PM4Py adapter (completed for the bounded circuit)

- Import CSV/XES and PNML.
- Group events by case ID and order them canonically.
- Call PM4Py's Petri-net alignment implementation outside the circuit.
- Normalize PM4Py tuples, including silent transitions, into the witness schema.
- Cross-check circuit-derived costs against PM4Py on every test case.

The witness adapter consumes the generated activity arrays and exact transition
indices. It deliberately ignores saved pre/post markings because the circuit
recomputes the marking after every move.

Use the public PM4Py API rather than copying student notebooks. Do not silently
sample cases or drop timeouts in correctness experiments.

### Stage 3 - bounded Petri-net circuit (completed for alignments up to 64 moves)

Represent the current marking inside the circuit. For every model-consuming
move, prove that input places have enough tokens and apply:

```text
next_marking = marking - input_vector + output_vector
```

The implementation uses sparse per-place transition incidence lists generated
from the real model. The next scalability task is increasing the alignment
bound from 64 toward the observed maximum after measuring proving resources.

### Stage 4 - committed log (single-trace circuit membership completed)

- Commit canonically indexed trace leaves into a Merkle root.
- Prove leaf membership for each trace.
- Batch proofs and bind batches to disjoint complete index ranges.
- Only claim whole-log conformance after omitted/duplicated cases are prevented.

The host-side SHA-256 append log remains the auditable storage layer. The gnark
adapter derives a circuit-friendly MiMC commitment and sparse-Merkle path from
the same 1,050 records, and the circuit verifies membership against a public
MiMC root. Batch proofs, complete disjoint index-range coverage, and recursive
aggregation remain future work.

### Stage 5 - optional extensions

- Private model via Merkle-committed transition membership.
- Global optimality via a zkVM proof of deterministic search or a complete
  product-graph shortest-path certificate.

Until Stage 5, describe the theorem as **valid alignment and verified cost**, not
"proof of optimal alignment."

## What can be reused from the student projects

Useful ideas:

- PM4Py PNML/XES loading.
- Alignment result parsing.
- Trace-variant grouping for performance experiments.

Do not directly reuse:

- assignment-specific paths and datasets;
- sampling and timeout exclusion logic;
- aggregate fitness formulas as circuit logic;
- notebook state or saved outputs as a source of truth.

The student projects solve conventional process-mining assignments. They do not
implement the six cryptographic validity checks or a proof system.

## Evaluation checklist

Measure search time separately from witness building and proof generation.
Report circuit constraints, proving time, verification time, peak memory, proof
size, and setup/key sizes while varying trace length, alignment length, model
size, and deviations. Correctness comes first: mutate each witness component and
confirm proof rejection.
