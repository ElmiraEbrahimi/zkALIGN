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

The first public model is the finite-state care pathway:

```text
Admit -> Examine -> Approve -> Treat -> Discharge
```

The demo trace replaces approval with an unexpected emergency test. It is
artificial and contains no real patient data.

## The six checks

1. **Binding:** recompute the salted commitment over domain, length, and padded
   activity IDs.
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

### Stage 0 - executable specification (included now)

- Tiny public finite-state healthcare model.
- Off-circuit Dijkstra alignment generator.
- Readable six-check reference verifier.
- Valid and adversarial test vectors.

This is the oracle for later circuit tests. It prevents debugging process logic
and cryptographic constraints simultaneously.

### Stage 1 - real gnark proof (initial fixed model included)

- Fixed capacities, e.g. 16 trace events and 24 alignment slots.
- Activity and move types encoded as integers.
- Public finite-state model compiled into constraints.
- MiMC commitment in both Go host code and circuit.
- Groth16 compile, setup, prove, and verify test.
- Exact-cost and threshold-only modes.

The finite-state version is the first publishable experiment because its
transition legality rule is simple and inspectable.

The included circuit fixes capacities at eight trace events and ten alignment
moves. This is deliberately a test-scale circuit, not a scalability claim.

### Stage 2 - PM4Py adapter (real-data baseline included)

- Import CSV/XES and PNML.
- Group events by case ID and order them canonically.
- Call PM4Py's Petri-net alignment implementation outside the circuit.
- Normalize PM4Py tuples, including silent transitions, into the witness schema.
- Cross-check circuit-derived costs against PM4Py on every test case.

The included Sepsis pipeline already performs the data split, Inductive Miner
discovery, held-out alignment, PNML/SVG export, transition-aware move parsing,
and pre/post marking reconstruction. The remaining Stage 2 work is to encode
those variable-size witnesses as bounded field arrays accepted by the Petri-net
circuit.

Use the public PM4Py API rather than copying student notebooks. Do not silently
sample cases or drop timeouts in correctness experiments.

### Stage 3 - bounded Petri-net circuit

Represent the current marking inside the circuit. For every model-consuming
move, prove that input places have enough tokens and apply:

```text
next_marking = marking - input_vector + output_vector
```

This is more faithful to PM4Py models than enumerating reachable markings, but
requires public capacity bounds and careful silent-transition tests.

### Stage 4 - committed multi-trace log (pre-ZKP layer included)

- Commit canonically indexed trace leaves into a Merkle root.
- Prove leaf membership for each trace.
- Batch proofs and bind batches to disjoint complete index ranges.
- Only claim whole-log conformance after omitted/duplicated cases are prevented.

The host-side implementation now commits all source traces, prevents occupied
leaf replacement, verifies membership and non-membership paths, hash-chains
every append checkpoint, and creates an exact coverage manifest for all held-out
alignments. These checks still need to be translated into circuit constraints;
the current JSON manifest must not be trusted by a verifier on its own.

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
