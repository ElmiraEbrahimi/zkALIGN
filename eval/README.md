# Reproducible single-trace evaluation

This directory implements the evaluation, not batching, recursion, or a private
model. Each public model/capacity configuration is compiled and set up separately.
The legacy Sepsis command remains available. Raw logs are cached under ignored
`datasets/raw/evaluation/`; witnesses and keys stay under ignored
`outputs/evaluation/`. Only compact research outputs are published.

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

## Commands

Install evaluation dependencies in the existing project environment:

```sh
.venv/bin/python -m pip install '.[evaluation]'
make eval-test
make eval
```

`make eval` runs sequentially: tests, four real cohorts, repeated stage timings,
capacity study, controlled synthetic models, root-only population scaling,
distinct-proof population audits, integrity checks, then reports. It can take hours. It does not commit, push, or
modify the manuscript. Do not run other CPU-heavy experiments concurrently when
collecting publication timings.

Individual steps:

```sh
make eval-core
PYTHONPATH=src .venv/bin/python -m eval.scalability --mode repeats
PYTHONPATH=src .venv/bin/python -m eval.scalability --mode setup-repeats
PYTHONPATH=src .venv/bin/python -m eval.scalability --mode capacity
PYTHONPATH=src .venv/bin/python -m eval.scalability --mode models
PYTHONPATH=src .venv/bin/python -m eval.scalability --mode population
PYTHONPATH=src .venv/bin/python -m eval.scalability --mode population-proofs
PYTHONPATH=src .venv/bin/python -m eval.scalability --mode integrity
make eval-report
PYTHONPATH=src .venv/bin/python -m eval.publish
```

The main run uses real proofs at K=1 and separate solver sensitivity checks at
K=0,2,3. For real proofs at all four thresholds, use `python -m eval.run
--thresholds 0 1 2 3 --solve-thresholds` with `PYTHONPATH=src` and the project
Python. A solver result is never added to the audit counter. The core runner saves
each completed case and resumes it; complete threshold runs also execute the
actual auditor over the saved certificates.

## Directory map and outputs

- `eval/data.py`: source retrieval, 80/20 case split, fixed random population,
  training-only Inductive Miner (noise 0.2), explicit unit-cost A* and replay.
- `eval/test_data.py`: independent Dijkstra reference on 200 tiny examples.
- `circuit/config*.go`: fixed public configuration; shared original constraints.
- `cmd/zkalign-eval/`: one operation per worker process, reusable serialized keys,
  public-context verification, integrity and root-reconstruction experiments.
- `eval/measure.py`: process-local peaks, sampling and 20 GiB/600 s worker guards.
- `eval/scalability.py`: model/capacity studies, paired timing repeats, population
  root reconstruction and invalid-input experiments.
- `eval/report.py`: CSV summaries, vector PDFs, a LaTeX section fragment and a
  source-indexed results README. Incomplete cohorts are not plotted as complete.

Artifacts under `outputs/evaluation/`:

```text
data/<dataset>/       frozen split, model, config, private cases, keys, proofs
  measurements/      raw JSON, stdout and stderr for every worker
capacity/<bound>/    same Sepsis model and AG witness at different capacities
scalability/<family>-<size>/  controlled synthetic fixed-capacity models
population/         fresh-process root-only measurements
population-audits/  actual distinct proofs for a fixed 100-case cohort
setup-repeats/      separate setup keys for five repetitions per model
results/            CSVs, environment.json, README.md, evaluation_results.tex
  figures/          eight vector-PDF plots when their measurements are available
```

The four cohorts have at most 300 held-out cases each. Every cohort member is
committed, including alignment timeouts or above-threshold cases. A cohort result
is **not** a certification of the complete source dataset. Sepsis uses a
384-move evaluation configuration; the legacy CLI's default remains 64.

Use `make eval`, not the legacy `make pre-zkp`, to reproduce the paper results.
The older healthcare demo uses PM4Py's high-level default search costs.
`eval.data.align` explicitly uses the circuit's 0/1 policy and bypasses the
fitness wrapper. Its oracle is tested against independent small-product search.

`eval.publish` checks experiment completeness and exports compact results to
`eval/results/`. It includes public-dataset splits/models for reproducibility,
but never private witness files, salts, or proving/verification keys. The larger
100,000-entry experiment measures root checking only. The 100- and 300-case
population experiments instead verify genuinely distinct certificates.

## Interpretation and limits

- `operation_seconds` is a monotonic wall-clock measurement around the named
  operation. `worker_seconds` includes startup, artifact loading and serialization.
- `process_peak_rss_bytes` is the OS high-water RSS of that one worker, not a
  difference of cumulative peaks. `sampled_operation_peak_rss_bytes` is absolute
  RSS observed during the operation; it is null when no sample hit a short stage.
- `witness` is `frontend.NewWitness` input encoding. The `solve` stage measures
  constraints separately; Groth16 proving also solves them internally. Do not
  add a diagnostic solver time to proving and call that the prover total.
- Peak memory includes required loaded keys/constraints. Python parent memory
  and the operating system's file cache are not attributed to the Go worker.
- `overhead.csv` pairs plaintext alignment, witness and proving for the same
  selected case/repetition. Setup is reported separately, not charged per trace.
- Repeated performance samples cover selected short, median and long alignments,
  plus Sepsis AG/NGA. They are not an estimate weighted by the source log's case
  frequencies. `thread_scaling.csv` reports both Go thread settings.
- `fig_trace_length.pdf` uses all certified Sepsis cases from the functional
  run. Those timings are observational; use the separate repeated timings for
  the primary performance results.
- Large-N root tests use synthetic distinct public commitments. They are not
  claimed to verify N distinct proofs. Real full-cohort audit verification is
  recorded by the `audit-k1` worker on each dataset.
- Synthetic nets are constructed directly as ordinary safe nets. The oracle
  tests cover small control-flow examples; generated real nets come from process
  trees. We do not claim an exhaustive reachability exploration of large nets.
- Salts and setup randomness are fresh. Seed 42 applies to data selection only.
  `sources.lock.json` contains project-local MiMC fingerprints of the compressed
  publisher files. Source metadata and frozen split files preserve provenance.
- Raw research case CSVs include reference costs. They are not the public audit
  interface. Actual proof bundles contain only commitment, proof and context hash.
- An expected rejection in a solver test is not a failed benchmark. Timeouts,
  capacity failures, oracle disagreements and unexpected verification errors
  are recorded distinctly; they must not be removed to improve the result.
