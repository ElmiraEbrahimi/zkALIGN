# Evaluation results

Saved observations and summaries for the four-log evaluation.

| Files | Contents |
| --- | --- |
| `datasets.csv`, `models/` | Model configurations and dataset metadata |
| `utility_*.csv`, `audit-reports/` | Threshold outcomes and audit evidence |
| `repeated_timings.csv`, `performance_summary.csv` | Per-case performance measurements |
| `repeated_setup.csv`, `setup_summary.csv` | Repeated compilation and setup |
| `capacity_performance_*.csv` | Alignment-capacity measurements |
| `scal_*.csv` | Model, trace, and population scalability |
| `integrity.csv` | Input-manipulation and audit checks |

Times are in seconds. Raw RSS fields are in bytes; memory plots use decimal MB.
Operation times exclude startup, artifact loading, and serialization, while
worker times include them. Standard deviations describe repeated observations.
Solver checks are recorded separately from verified proofs.

The historical synthetic-model results here use three repetitions. Independent
ten-repeat runs are saved under `outputs/scalability-ten/`; they do not replace
these observations. See [evaluation](../README.md) and [plotting](../plotting/README.md)
for reproduction commands.
