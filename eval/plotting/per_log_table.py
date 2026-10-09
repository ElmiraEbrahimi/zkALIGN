"""Export the per-log performance table's exact saved statistics; no benchmark."""

import csv
from pathlib import Path


def generate(results=Path("eval/results"), output=Path("eval/plotting/data/tab_per_log_performance.csv")):
    def read(name):
        with (results / name).open(newline="") as stream:
            return list(csv.DictReader(stream))

    setup = read("setup_summary.csv")
    performance = read("performance_summary.csv")
    artifacts = {row["dataset"]: row for row in read("artifact_sizes.csv")}
    rows = []
    for dataset in ("bpic13cp", "rtfm", "sepsis", "hospital"):
        for stage in ("compile", "setup", "witness", "prove", "verify"):
            source = "setup_summary.csv" if stage in ("compile", "setup") else "performance_summary.csv"
            candidates = setup if stage in ("compile", "setup") else performance
            def statistic(metric):
                matching = [r for r in candidates if r["dataset"] == dataset and r["stage"] == stage and r["metric"] == metric]
                if len(matching) != 1:
                    raise ValueError(f"Missing or duplicate statistic: {dataset} {stage} {metric}")
                return matching[0]
            memory = statistic("process_peak_rss_bytes")
            time = statistic("operation_seconds")
            expected = 5 if stage in ("compile", "setup") else 20 if dataset == "sepsis" else 15
            if int(memory["n"]) != expected or int(time["n"]) != expected:
                raise ValueError("Unexpected measurement count")
            artifact = artifacts[dataset]
            for kind in ("pk", "vk", "proof"):
                if artifact[f"{kind}_min_bytes"] != artifact[f"{kind}_max_bytes"]:
                    raise ValueError(f"Artifact sizes vary: {dataset} {kind}")
            rows.append(dict(
                dataset=dataset, stage=stage, K="" if stage in ("compile", "setup") else 1,
                observations=expected, memory_mean_mb=float(memory["mean"])/1e6,
                memory_sd_mb=float(memory["std"])/1e6,
                operation_time_mean_s=float(time["mean"]), operation_time_sd_s=float(time["std"]),
                pk_bytes=int(artifact["pk_min_bytes"]), vk_bytes=int(artifact["vk_min_bytes"]),
                proof_bytes=int(artifact["proof_min_bytes"]), source=str(results/source),
                artifact_source=str(results/"artifact_sizes.csv"),
                memory_scope="whole-process OS peak RSS; MB = 1000000 bytes",
                time_scope="operation only; excludes startup, artifact loading and serialization",
                aggregation="five setup repeats" if stage in ("compile", "setup") else "pooled selected cases, five repeats per case",
            ))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['dataset']:10} {row['stage']:7} {row['memory_mean_mb']:.1f} +/- {row['memory_sd_mb']:.1f} MB; {row['operation_time_mean_s']:.6f} s")
    print(output)


if __name__ == "__main__":
    generate()
