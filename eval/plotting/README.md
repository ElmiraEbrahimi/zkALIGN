# Evaluation figures from saved measurements

This folder contains plotting code and one dedicated CSV for each figure.
No plotting or reporting command compiles circuits, generates proofs, or runs benchmarks.

## Final performance table and figures

Use `tab_per_log_performance.csv` for the per-log memory table,
`fig_plaintext_comparison.pdf` for plaintext versus zkALIGN operation times,
and `fig_capacity_performance.pdf` for fresh-process time and peak RSS versus
capacity. The two figures have different timing scopes, recorded in their CSVs.
Generate these outputs from saved measurements with:

```sh
PYTHONPATH=src .venv/bin/python -m eval.plotting.per_log_table
PYTHONPATH=src .venv/bin/python -m eval.plotting.plaintext_comparison
PYTHONPATH=src .venv/bin/python -m eval.plotting.capacity_performance
```

The plaintext comparison uses short, median and long cases only, with alignment
lengths shown below each pair. It excludes the additional Sepsis case AG.
The per-log summary retains the original measurements including AG and must
not be described as having the same selected sample as the comparison figure.
Both exporters use the committed `eval/results/` observations by default.
The capacity command requires the local raw run and measurement receipts under
`outputs/evaluation/capacity-performance/`; run the benchmark in `eval/README.md`
first on a fresh checkout.

The alternative `python -m eval.plotting.overhead` keeps the overhead-ratio figure
available. It independently checks 65 paired repetitions against the raw stage
measurements and selected-case summary. Do not interpret its ratios as
fresh-process end-to-end latency or estimates for the entire log.
New memory plots use decimal MB consistently (1 MB = 1,000,000 bytes).
Historical PDFs, including operation-only archives, are not silently relabelled.
The four-log categorical stage plots are retained as alternatives, not extra
figures for the final paper. Their plotting code also uses MB when regenerated.

The OS process peak is used, not the 5 ms sampled operation peak. All 25 witness
operations in the controlled capacity run have no in-operation RSS sample, so
replacing process peaks with those samples would remove that series or imply
unsupported zero memory. The diagnostic compiler/prover heap profiles explain
allocation patterns; they are not replacements for benchmark repeats.

Draw the **controlled capacity performance figure** after the five-repeat run:

```sh
PYTHONPATH=src .venv/bin/python -m eval.plotting.capacity_performance
```

This validates all 125 stage observations (including 25 successful verifications)
and checks means and sample SDs against the raw data and measurement JSON files.
It writes `data/fig_capacity_performance.csv` and
`eval/results/figures/fig_capacity_performance.pdf`, leaving previous figures intact.
Only compilation, setup, witness construction and proving are plotted.
The x-axis is alignment capacity, with Sepsis, AG's 18 moves, trace capacity 185,
K=1 and the thread count fixed. Time is **whole-stage harness elapsed time**
(`worker_seconds`), including process startup, loading, computation and output,
in seconds on a logarithmic axis. Memory is whole-process peak RSS in decimal MB
on a linear axis. Error bars are +/- one
sample SD over five repetitions. Lines connect observations, not fitted trends.
This measures larger circuit capacities, not progressively longer input traces.
The figure CSV explicitly separates `worker_time_*` from `operation_time_*`.
`eval/results/capacity_performance_summary.csv` retains both timing definitions
and includes verification for textual reporting. Original run CSVs are not changed.
The old operation-only PDF/CSV are archived with the `_operation_only` suffix.
Input-witness encoding only encodes supplied inputs; internal-wire solving is
part of proving. Its whole-stage time is dominated by startup/I/O and includes
the harness's 5 ms polling granularity; it is not a pure witness-algorithm timing.

Redraw **only the two performance figures** from saved repeated summaries:

```sh
PYTHONPATH=src .venv/bin/python -m eval.plotting.performance
```

`fig_setup_time_memory.pdf` compares compilation and setup.
`fig_time_memory.pdf` compares witness construction and proof generation only.
Verification remains in the result summaries for reporting in the text.
Each PDF has its own CSV under `data/`, containing precisely the plotted metrics,
their means, sample standard deviations and observation counts. Figures are
12.2 by 5.3 cm, with muted blue/red series and logarithmic time and memory axes.
Error bars are mean +/- one sample SD, even when smaller than the marker.
Compilation/setup use five observations per configuration. Witness/proving pool
five repetitions of each selected case (15 observations per smaller log and 20
for Sepsis). Their SD includes differences between selected cases, not just
repeat-to-repeat variation. Peak RSS is the whole isolated process peak,
including loaded inputs and keys, not the operation's incremental allocation.

Refresh **only the utility figure** from the completed local all-threshold run:

```sh
PYTHONPATH=src .venv/bin/python -m eval.plotting.utility
```

This reads `outputs/evaluation/results/utility_summary.csv`, rejects missing,
duplicate, incomplete, erroneous, or solver-only configurations, and saves
`eval/plotting/data/fig_utility.csv` and `eval/results/figures/fig_utility.pdf`.
The PDF is 12.2 cm wide and 4.8 cm high, with Times-style type and the muted
red `#8c2d26` / blue `#2171b5` reference palette. Nested markers keep both
series visible when equal. All panels use the same percentage scale.
No error bars are added to exact cohort proportions. Above-threshold cases
remain uncertified without a proof attempt, so the figure is not an invalid-proof
rejection experiment. The CSV preserves all source counts and adds the plotted
percentages. Other figures and performance measurements are untouched.

Refresh summaries and figures from the locally published observations:

```sh
PYTHONPATH=src .venv/bin/python -m eval.report --root eval
```

Redraw figures using only their dedicated CSVs:

```sh
PYTHONPATH=src .venv/bin/python -m eval.plotting.draw
```

Figures are written to `eval/results/figures/`. They remain local paper assets.
The `data/fig_*.csv` filenames match the corresponding PDF filenames.
Blue/red match the primary zkPACT plotting colors. Green/purple distinguish
additional series, as in ZERUS. Markers and line styles also distinguish series.

| Figure | Source and interpretation |
| --- | --- |
| Utility | All four thresholds, fixed cohort denominator. Blue squares count actual Groth16 certificates; red circles show the reference. Optional diagnostic solver rows use triangles, never certification. The percentage axis is zoomed and explicitly labelled. Utility uses the ZERUS muted palette (#8c2d26 and #2171b5). |
| Overhead | One point per selected case, five paired repeats. Mean plus/minus sample SD. Dashed line is the median of selected case means, not a population estimate. |
| Model scalability | Three proof repeats per configuration, mean plus/minus sample SD. CSV includes places, transitions, arcs and constraints. These covary, so no single-variable causal explanation is established. |
| Time/memory | Selected-case repeated means plus/minus sample SD, default threads only. Memory is whole-process peak RSS. |
| Compilation/setup | Dedicated five-repeat benchmark, not the earlier functional-run measurements. |
| Capacity | Deterministic circuit counts and cohort coverage; these do not need statistical error bars. |
| Trace length | Single functional-run observations for certified Sepsis cases, overlaid with median and full min-max range for the four repeated selected cases. No repeated observations are invented for the others. |
| Population | Mean plus/minus sample SD for three root-validation repetitions per synthetic roster size. This is not proof verification throughput. |

## Overhead definition

Each repetition's prover operation time is alignment + witness encoding + proving.
Its overhead factor is that sum divided by the same repetition's plaintext
alignment time. Setup, loading, serialization and auditor verification are excluded.
`overhead_summary.csv` contains both case rows and explicitly labelled selected-sample
dataset rows. `dataset_median_case_overhead` is the median of the selected cases'
mean ratios. `operation_overhead_median` is the median of paired repetition ratios.
The SD of pooled dataset rows includes differences between cases and must not be
presented as within-case timing variability. Blank SD means fewer than two samples.

Role labels can overlap. A case selected as both `long` and `NGA` is counted once.
Case identifiers in these research outputs refer to public datasets and should
not be included in a real private auditor package.
