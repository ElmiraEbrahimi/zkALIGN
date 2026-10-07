# Evaluation results

Generated from raw stage measurements. A solver success is not a proof.
Research-only case CSVs can contain costs/IDs; do not include them in a live auditor package.
Memory is RSS in bytes (plots use MiB). OS peaks are per fresh process, including input loading and serialization.
Operation times exclude loading/serialization. Worker times include them. Witness means gnark input encoding; proving includes constraint solving.
Main-cohort timings are functional-run observations; repeated timings are the performance sample.

- bpic13cp, K=0, solver: processed 297/297, reference-qualified 270, certified nan, errors 0. Source: utility_summary.csv.
- bpic13cp, K=1, groth16: processed 297/297, reference-qualified 293, certified 293.0, errors 0. Source: utility_summary.csv.
- bpic13cp, K=2, solver: processed 297/297, reference-qualified 297, certified nan, errors 0. Source: utility_summary.csv.
- bpic13cp, K=3, solver: processed 297/297, reference-qualified 297, certified nan, errors 0. Source: utility_summary.csv.
- hospital, K=0, solver: processed 300/300, reference-qualified 262, certified nan, errors 0. Source: utility_summary.csv.
- hospital, K=1, groth16: processed 300/300, reference-qualified 300, certified 300.0, errors 0. Source: utility_summary.csv.
- hospital, K=2, solver: processed 300/300, reference-qualified 300, certified nan, errors 0. Source: utility_summary.csv.
- hospital, K=3, solver: processed 300/300, reference-qualified 300, certified nan, errors 0. Source: utility_summary.csv.
- rtfm, K=0, solver: processed 300/300, reference-qualified 297, certified nan, errors 0. Source: utility_summary.csv.
- rtfm, K=1, groth16: processed 300/300, reference-qualified 299, certified 299.0, errors 0. Source: utility_summary.csv.
- rtfm, K=2, solver: processed 300/300, reference-qualified 300, certified nan, errors 0. Source: utility_summary.csv.
- rtfm, K=3, solver: processed 300/300, reference-qualified 300, certified nan, errors 0. Source: utility_summary.csv.
- sepsis, K=0, solver: processed 210/210, reference-qualified 144, certified nan, errors 0. Source: utility_summary.csv.
- sepsis, K=1, groth16: processed 210/210, reference-qualified 195, certified 195.0, errors 0. Source: utility_summary.csv.
- sepsis, K=2, solver: processed 210/210, reference-qualified 204, certified nan, errors 0. Source: utility_summary.csv.
- sepsis, K=3, solver: processed 210/210, reference-qualified 210, certified nan, errors 0. Source: utility_summary.csv.

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
- bpic13cp compile: operation 0.137131 s, process RSS 119.81 MiB. Source: measurements.csv, measurement=compile.
- bpic13cp setup: operation 1.163871 s, process RSS 95.83 MiB. Source: measurements.csv, measurement=setup.
- hospital compile: operation 0.381053 s, process RSS 128.17 MiB. Source: measurements.csv, measurement=compile.
- hospital setup: operation 1.539555 s, process RSS 104.47 MiB. Source: measurements.csv, measurement=setup.
- rtfm compile: operation 0.093433 s, process RSS 64.73 MiB. Source: measurements.csv, measurement=compile.
- rtfm setup: operation 1.337697 s, process RSS 59.91 MiB. Source: measurements.csv, measurement=setup.
- sepsis compile: operation 2.001006 s, process RSS 1913.20 MiB. Source: measurements.csv, measurement=compile.
- sepsis setup: operation 33.804120 s, process RSS 1036.94 MiB. Source: measurements.csv, measurement=setup.

## Completeness
Missing experiment files: none
