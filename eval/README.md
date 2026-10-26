# Evaluation

Run commands from the repository root after installing `.[evaluation]`.
The evaluation uses the four datasets listed in [datasets/README.md](../datasets/README.md).

## Complete evaluation

```bash
make eval
```

This runs tests, four-log proof experiments, performance and scalability
benchmarks, integrity checks, and reporting. Results are saved under
`outputs/evaluation/results/`. Run benchmarks without competing CPU-heavy jobs.

## Individual experiments

```bash
make eval-test
make eval-core
make eval-scalability
make eval-report
```

The core experiment evaluates thresholds 0, 1, 2, and 3. To check above-threshold
witnesses separately:

```bash
PYTHONPATH=src .venv/bin/python -m eval.above_threshold
```

For the five-repeat alignment-capacity benchmark:

```bash
go build -o build/zkalign-eval ./cmd/zkalign-eval
PYTHONPATH=src .venv/bin/python -m eval.capacity_performance --repeat 5 --threads 14
```

For ten repetitions of all 24 synthetic models, after `make eval-scalability`:

```bash
PYTHONPATH=src .venv/bin/python -m eval.scalability_ten --threads 14
```

Each ten-repeat run creates a separate directory under
`outputs/scalability-ten/`. See [scalability_ten/README.md](scalability_ten/README.md)
for plotting and output filenames.

Optional five-repeat reruns of the real-log, capacity, and synthetic-model
performance experiments use independent output directories:

```bash
PYTHONPATH=src .venv/bin/python -m eval.performance_rerun_v2 --repeat 5 --threads 14
```

## Results

Operation time excludes startup, artifact loading, and serialization.
Memory is the operating system's peak RSS of each fresh worker process;
plot values use decimal MB. Error bars show sample standard deviations.

Committed numerical results are in [results/](results/).
[plotting/README.md](plotting/README.md) explains how to regenerate figures
without rerunning experiments. Private inputs and cryptographic artifacts stay
under Git-ignored `outputs/`.
