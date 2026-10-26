"""Small witness-only diagnostic, separate from the full paper benchmark."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid

from eval.measure_fresh_v2 import stage
from eval.performance_rerun_v2 import (
    ROOT, digest, make_specs, schedule, statistics_for, write_csv, write_json,
)


def main():
    run = ROOT / "outputs/witness-smoke-v2" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    run.mkdir(parents=True, mode=0o700)
    binary = run / "zkalign-eval"
    shutil.copy2(ROOT / "build/zkalign-eval", binary)
    source = ROOT / "outputs/evaluation"
    specs = make_specs(source, ("capacity",))
    hashes = {str(source / "data/sepsis" / name): digest(source / "data/sepsis" / name)
              for name in ("config.json", "cases.json")}
    jobs = schedule(specs, 5, 20261021)
    write_json(run / "manifest.json", dict(
        purpose="Witness-only smoke test, not a full performance rerun",
        repetitions=5, threads=14, schedule=jobs, source_hashes=hashes,
        binary_sha256=digest(binary), measurement_method="blocking_wait4_v2",
        note="Prepare once per capacity; no excluded warmup or forced cache flushing."
    ))
    print(f"SMOKE OUTPUT: {run}", flush=True)
    for spec in specs:
        folder = run / spec["id"]
        write_json(folder / "config.json", spec["config"])
        write_json(folder / "cases.json", spec["cases"])
        result = stage(binary, folder, "prepare", threads=14)
        if result.get("status") != "ok" or result["exit_code"]:
            raise RuntimeError(f"Preparation failed: {result['measurement_file']}")
    rows = []
    for job in jobs:
        spec = specs[job["spec_index"]]
        folder = run / spec["id"]
        tag = f"witness-{job['repeat']}"
        result = stage(binary, folder, "witness", case=folder / "private-0.json",
                       threads=14, tag=tag, prefix=tag)
        if result.get("status") != "ok" or result["exit_code"]:
            raise RuntimeError(f"Witness failed: {result['measurement_file']}")
        rows.append(dict(capacity=spec["config"]["alignment_capacity"],
                         repeat=job["repeat"], order=job["order"],
                         **{k:v for k,v in result.items() if not isinstance(v, (dict,list))}))
        write_csv(run / "witness_runs.csv", rows)
    summaries = []
    for spec in specs:
        capacity = spec["config"]["alignment_capacity"]
        summary = dict(capacity=capacity, **statistics_for([r for r in rows if r["capacity"] == capacity]))
        summaries.append(summary)
        print(f"{capacity:3d}: operation {summary['operation_time_mean_s']*1000:.3f} +/- "
              f"{summary['operation_time_sd_s']*1000:.3f} ms; process "
              f"{summary['worker_time_mean_s']*1000:.3f} +/- "
              f"{summary['worker_time_sd_s']*1000:.3f} ms", flush=True)
    write_csv(run / "witness_summary.csv", summaries)
    if any(digest(path) != value for path,value in hashes.items()):
        raise RuntimeError("Source input changed during diagnostic")
    write_json(run / "complete.json", dict(status="ok", witness_processes=len(rows),
                                          scope="witness encoding only; no proof validation"))


if __name__ == "__main__":
    main()
