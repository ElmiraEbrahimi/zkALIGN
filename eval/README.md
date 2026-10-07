# Reproducible single-trace evaluation

This directory implements the evaluation, not batching, recursion, or a private
model. Each public model/capacity configuration is compiled and set up separately.
The legacy Sepsis command remains available. Raw logs, witnesses and keys are
stored in ignored `outputs/evaluation/`; only compact measurements are published.

## Staged development

1. Generalize the fixed circuit configuration without duplicating constraints;
   retain and test the legacy Sepsis configuration.
2. Establish explicit unit-cost alignment ground truth and frozen, whole-root
   evaluation populations for four public datasets.
3. Isolate compile, setup, witness, prove and verify in separate processes.
4. Test threshold utility, malicious witnesses and population accounting.
5. Run controlled model/capacity/length/population experiments and export tables.

Each stage is tested and committed separately. Do not treat a solver result as a
certificate. Failed or over-capacity cases remain in their frozen denominator.

## Measurement contract

The Veriblock-FL reference runs ZoKrates stages as subprocesses and samples RSS.
We retain stage separation and use a new OS process for **every stage and repeat**.
Report operation wall time (excluding artifact loading), total worker wall time,
absolute sampled operation RSS, and OS process high-water RSS separately. Setup
and proof memory includes their required in-memory inputs; it is not obtained by
subtracting unrelated high-water marks. Sampling can miss sub-interval peaks.
No `RUSAGE_CHILDREN` cumulative maximum is attributed to a later child. Record
per-child `wait4` usage instead. OS peak includes loading and serialization.

Reference revisions inspected

- Veriblock-FL `e0a66df7b9ce89a3d42f39e2044d49e714736926`,
  `verification/time_memory_analytics/analyze.py`.
- zkPACT `882d9eac94248ed96ac890672238b3a36efa2dee`,
  `go-server/internal/memtime/`.

Baseline before this work: `go test ./...` passed; Python unittest suite passed
12 tests. Existing application MiMC domains and audit v4 are preserved. Production
setup trust and independently authenticated roots remain deployment requirements.
