# Ten-repeat model scalability

This benchmark reuses the 24 model configurations and keys created by
`make eval-scalability`. It generates and verifies ten proofs per model,
with randomized model order in each repetition.

From the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m eval.scalability_ten --threads 14
```

Each invocation creates a new directory under `outputs/scalability-ten/`.
The runner prints its path. Existing runs and baseline results are preserved.

- `ten_scalability_runs.csv`: individual stage measurements.
- `ten_model_scalability.csv`: means, sample standard deviations, and ranges.
- `ten_manifest.json`: configuration and input fingerprints.
- `ten_complete.json`: successful completion of all 240 proofs.

Generate the figure from a completed run:

```bash
PYTHONPATH=src .venv/bin/python -m eval.scalability_ten.plot --run outputs/scalability-ten/RUN_DIRECTORY
```

Replace `RUN_DIRECTORY` with the printed directory name. The figure is saved as
`figures/caise_model_scalability-ten.pdf` inside that directory. It reports
operation-only proof time with sample-standard-deviation error bars.
Interrupted runs retain partial observations but do not produce a final summary.
