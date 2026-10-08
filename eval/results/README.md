# Evaluation results

Generated from raw stage measurements. A solver success is not a proof.
Research-only case CSVs can contain costs/IDs; do not include them in a live auditor package.
Memory is RSS in bytes (plots use MiB). OS peaks are per fresh process, including input loading and serialization.
Operation times exclude loading/serialization. Worker times include them. Witness means gnark input encoding; proving includes constraint solving.
Main-cohort timings are functional-run observations; repeated timings are the performance sample.


## Repeated performance samples
- bpic13cp alignment operation_seconds: mean 0.00149947227, SD 0.00139999821, n=15. Source: performance_summary.csv / repeated_timings.csv.
- bpic13cp alignment process_peak_rss_bytes: mean 158955383, SD 601217.434, n=15. Source: performance_summary.csv / repeated_timings.csv.
- bpic13cp prove operation_seconds: mean 0.115361803, SD 0.00169518308, n=15. Source: performance_summary.csv / repeated_timings.csv.
- bpic13cp prove process_peak_rss_bytes: mean 125063441, SD 2790839.96, n=15. Source: performance_summary.csv / repeated_timings.csv.
- bpic13cp verify operation_seconds: mean 0.000881169467, SD 2.2590717e-05, n=15. Source: performance_summary.csv / repeated_timings.csv.
- bpic13cp verify process_peak_rss_bytes: mean 10508697.6, SD 154913.298, n=15. Source: performance_summary.csv / repeated_timings.csv.
- bpic13cp witness operation_seconds: mean 0.000124949933, SD 2.30233548e-05, n=15. Source: performance_summary.csv / repeated_timings.csv.
- bpic13cp witness process_peak_rss_bytes: mean 8324164.27, SD 152752.848, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital alignment operation_seconds: mean 0.00356426107, SD 0.0033151438, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital alignment process_peak_rss_bytes: mean 160043281, SD 630471.34, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital prove operation_seconds: mean 0.110267306, SD 0.00400495418, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital prove process_peak_rss_bytes: mean 131706607, SD 3892893.3, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital verify operation_seconds: mean 0.0008700612, SD 3.0148374e-05, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital verify process_peak_rss_bytes: mean 10516343.5, SD 144814.365, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital witness operation_seconds: mean 0.000109811067, SD 7.36658416e-06, n=15. Source: performance_summary.csv / repeated_timings.csv.
- hospital witness process_peak_rss_bytes: mean 8296857.6, SD 85313.7483, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm alignment operation_seconds: mean 0.0017240638, SD 0.000288683683, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm alignment process_peak_rss_bytes: mean 158816666, SD 517433.594, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm prove operation_seconds: mean 0.0827760613, SD 0.00205162185, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm prove process_peak_rss_bytes: mean 73808827.7, SD 3394508.29, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm verify operation_seconds: mean 0.000865227733, SD 1.82517224e-05, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm verify process_peak_rss_bytes: mean 10503236.3, SD 96028.1055, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm witness operation_seconds: mean 7.99612667e-05, SD 9.18318133e-06, n=15. Source: performance_summary.csv / repeated_timings.csv.
- rtfm witness process_peak_rss_bytes: mean 8257536, SD 86916.8608, n=15. Source: performance_summary.csv / repeated_timings.csv.
- sepsis alignment operation_seconds: mean 0.159379196, SD 0.279819486, n=20. Source: performance_summary.csv / repeated_timings.csv.
- sepsis alignment process_peak_rss_bytes: mean 174228275, SD 25300871.9, n=20. Source: performance_summary.csv / repeated_timings.csv.
- sepsis prove operation_seconds: mean 0.636485, SD 0.018067826, n=20. Source: performance_summary.csv / repeated_timings.csv.
- sepsis prove process_peak_rss_bytes: mean 1.10435287e+09, SD 4445866.6, n=20. Source: performance_summary.csv / repeated_timings.csv.
- sepsis verify operation_seconds: mean 0.0008739791, SD 2.1120489e-05, n=20. Source: performance_summary.csv / repeated_timings.csv.
- sepsis verify process_peak_rss_bytes: mean 10024550.4, SD 129802.016, n=20. Source: performance_summary.csv / repeated_timings.csv.
- sepsis witness operation_seconds: mean 0.00029242085, SD 1.48224008e-05, n=20. Source: performance_summary.csv / repeated_timings.csv.
- sepsis witness process_peak_rss_bytes: mean 8495104, SD 106246.964, n=20. Source: performance_summary.csv / repeated_timings.csv.
- Integrity attempts 3471, unexpected outcomes 0, inapplicable mutations 373. Source: integrity.csv.
- Negative integrity attempts 3263, unexpected outcomes 0. Valid controls and duplicate-count invariants are reported separately in integrity.csv.
- Distinct-certificate audit N=100: 100 certified, 0.077958 s audit operation. Source: scal_population_proofs.csv.
- Distinct-certificate audit N=300: 299 certified, 0.233085 s audit operation. Source: scal_population_proofs.csv.

## Repeated compilation and setup
- bpic13cp compile: 0.13 s (SD 0.00), n=5. Source: setup_summary.csv / repeated_setup.csv.
- bpic13cp setup: 1.27 s (SD 0.06), n=5. Source: setup_summary.csv / repeated_setup.csv.
- hospital compile: 0.23 s (SD 0.00), n=5. Source: setup_summary.csv / repeated_setup.csv.
- hospital setup: 1.30 s (SD 0.05), n=5. Source: setup_summary.csv / repeated_setup.csv.
- rtfm compile: 0.04 s (SD 0.00), n=5. Source: setup_summary.csv / repeated_setup.csv.
- rtfm setup: 0.78 s (SD 0.02), n=5. Source: setup_summary.csv / repeated_setup.csv.
- sepsis compile: 1.98 s (SD 0.04), n=5. Source: setup_summary.csv / repeated_setup.csv.
- sepsis setup: 8.76 s (SD 0.13), n=5. Source: setup_summary.csv / repeated_setup.csv.

## Interpretation
overhead_summary.csv separates each selected case from the pooled selected sample. It is not a population-wide estimate.
Prover operation time = alignment + witness encoding + proving. Overhead is that sum divided by alignment time for each paired repetition; setup, loading and verification are excluded.
dataset_median_case_overhead is the median of the selected cases' mean paired overhead ratios. operation_overhead_median is the median of individual paired ratios.
Error bars denote sample standard deviation (not confidence intervals). Model scaling has three repeats; per-case overhead has five.
scal_model_summary.csv reports places, transitions and arcs as well as constraints. Larger parallel nets are associated with higher circuit cost; these measurements do not isolate a single causal factor.
scal_length.csv contains functional-run observations. scal_length_repeated.csv contains medians and ranges for only the selected repeated Sepsis cases.
Each figure has its own source CSV under plotting/data. Plotting and reporting never start benchmark workers.
A population of 300 included 299 accepted certificates, not 300. Large synthetic roster timings are root checks only.

## Completeness
Missing experiment files: none

<!-- utility-results:start -->
## Utility preservation

All four thresholds use real Groth16 proofs. Verified proofs: 4,268.
Only reference-qualified cases are proved. Above-threshold cases remain uncertified without a proof attempt.
Thus utility measures successful certification coverage, not adversarial rejection or universal soundness.
The earlier interrupted run log is historical; completed per-case records and all 16 audit reports are the evidence.
Source: utility_summary.csv, utility_cases.csv, and audit-reports/<dataset>-k<K>.json.

- bpic13cp, K=0: reference-qualified 270, certified 270/297, errors 0, capacity misses 0.
- bpic13cp, K=1: reference-qualified 293, certified 293/297, errors 0, capacity misses 0.
- bpic13cp, K=2: reference-qualified 297, certified 297/297, errors 0, capacity misses 0.
- bpic13cp, K=3: reference-qualified 297, certified 297/297, errors 0, capacity misses 0.
- rtfm, K=0: reference-qualified 297, certified 297/300, errors 0, capacity misses 0.
- rtfm, K=1: reference-qualified 299, certified 299/300, errors 0, capacity misses 0.
- rtfm, K=2: reference-qualified 300, certified 300/300, errors 0, capacity misses 0.
- rtfm, K=3: reference-qualified 300, certified 300/300, errors 0, capacity misses 0.
- sepsis, K=0: reference-qualified 144, certified 144/210, errors 0, capacity misses 0.
- sepsis, K=1: reference-qualified 195, certified 195/210, errors 0, capacity misses 0.
- sepsis, K=2: reference-qualified 204, certified 204/210, errors 0, capacity misses 0.
- sepsis, K=3: reference-qualified 210, certified 210/210, errors 0, capacity misses 0.
- hospital, K=0: reference-qualified 262, certified 262/300, errors 0, capacity misses 0.
- hospital, K=1: reference-qualified 300, certified 300/300, errors 0, capacity misses 0.
- hospital, K=2: reference-qualified 300, certified 300/300, errors 0, capacity misses 0.
- hospital, K=3: reference-qualified 300, certified 300/300, errors 0, capacity misses 0.
<!-- utility-results:end -->

## Above-threshold utility checks

All 160 above-threshold case-threshold pairs were checked with the gnark R1CS
solver using the saved PM4Py alignment and its true cost. All 160 witnesses
were rejected by unsatisfied constraints. There were no unexpected satisfactions
or execution errors. No additional Groth16 proofs were generated.

| Dataset | K=0 rejected/tested | K=1 rejected/tested | K=2 rejected/tested | K=3 |
| --- | --- | --- | --- | --- |
| BPI 2013 Closed Problems | 27/27 | 4/4 | 0/0 | 0/0 |
| Road Traffic Fines | 3/3 | 1/1 | 0/0 | 0/0 |
| Sepsis Cases | 66/66 | 15/15 | 6/6 | 0/0 |
| Hospital Billing | 38/38 | 0/0 | 0/0 | 0/0 |
| Total | 134/134 | 20/20 | 6/6 | 0/0 |

The 140 K=0/K=2 rows were recovered from `utility-before-groth16.json` archives
and checked against their saved solver receipts and frozen case metadata.
The 20 K=1 rows were newly executed using the existing `solve` stage.
Source: `utility_above_threshold.csv`, `utility_above_threshold_receipts.json`,
and the `above_threshold_cases` / `above_threshold_rejected` columns in
`utility_summary.csv`. The Groth16 case file and figure counts are unchanged.
Solver rejection establishes failure of the supplied witness, not an exhaustive
search over all possible alignments. The circuit and cost policy are unchanged.
