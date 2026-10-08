# Evaluation figures from saved measurements

This folder contains plotting code and one dedicated CSV for each figure.
No plotting or reporting command compiles circuits, generates proofs, or runs benchmarks.

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
