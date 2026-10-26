# Plotting

These commands read saved measurements and do not run benchmarks.
Run them from the repository root after installing `.[evaluation]`.

## Saved figures

```bash
PYTHONPATH=src .venv/bin/python -m eval.plotting.draw
PYTHONPATH=src .venv/bin/python -m eval.plotting.caise
```

Both read the committed CSVs in `eval/plotting/data/` and write PDFs to
`eval/results/figures/`. The compact exports use the `caise_` prefix.
Their capacity plot uses complete-process time; the other timing plots use
operation time. Historical model-scaling CSVs contain three repetitions.

For the operation-time capacity figure, after the capacity benchmark:

```bash
PYTHONPATH=src .venv/bin/python -m eval.plotting.capacity_operation
```

This validates the local benchmark receipts and writes
`caise_capacity_operation_time.pdf`. Memory remains whole-process peak RSS.

## Ten-repeat model scalability

```bash
PYTHONPATH=src .venv/bin/python -m eval.scalability_ten.plot --run outputs/scalability-ten/RUN_DIRECTORY
```

Replace `RUN_DIRECTORY` with the completed run directory printed by the
benchmark. The PDF is saved inside that run as
`figures/caise_model_scalability-ten.pdf`.

Times are in seconds, memory is in decimal MB, and error bars show sample
standard deviations. The ten-repeat plotter checks all 240 verification
outcomes and reconciles the summary with the raw observations.
