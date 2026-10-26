"""Reuse saved circuits and keys, writing only into a unique new run folder."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import sys
import uuid

from eval.measure_fresh_v2 import stage

ROOT = Path(__file__).resolve().parents[2]
FAMILIES = ("sequence", "choice", "parallel", "loop")
SIZES = (5, 10, 20, 30, 40, 50)
REPETITIONS = 10
FILES = ("config.json", "cases.json", "private-0.json", "circuit.r1cs",
         "proving.key", "verification.key", "manifest-1.json", "manifest-1.mimc",
         "population.json")
FIELDS = ("family", "activities", "repeat", "order", "stage", "threads", "K",
          "places", "transitions", "arcs", "constraints", "trace_capacity",
          "alignment_capacity", "pk_bytes", "operation_seconds", "worker_seconds",
          "process_peak_rss_bytes", "user_cpu_seconds", "system_cpu_seconds",
          "status", "exit_code", "pid", "certified", "proof_bytes", "bundle_bytes",
          "measurement_file", "error")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_new(path, data):
    with Path(path).open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def read_specs(source):
    specs = []
    for family in FAMILIES:
        for size in SIZES:
            folder = source / f"{family}-{size}"
            for name in FILES + ("measurements/compile.json",):
                if not (folder / name).is_file():
                    raise FileNotFoundError(folder / name)
            cfg = json.loads((folder / "config.json").read_text())
            compiled = json.loads((folder / "measurements/compile.json").read_text())
            manifest = json.loads((folder / "manifest-1.json").read_text())
            if manifest.get("threshold") != 1:
                raise ValueError(f"Unexpected audit threshold: {folder}")
            if cfg["trace_capacity"] != 128 or cfg["alignment_capacity"] != 256:
                raise ValueError(f"Unexpected capacities: {folder}")
            if compiled["status"] != "ok" or compiled["constraints"] <= 0:
                raise ValueError(f"Invalid compilation receipt: {folder}")
            specs.append(dict(family=family, activities=size, source=folder,
                              places=len(cfg["initial"]), transitions=len(cfg["labels"]),
                              arcs=sum(map(len, cfg["inputs"] + cfg["outputs"])),
                              constraints=compiled["constraints"], trace_capacity=128,
                              alignment_capacity=256, pk_bytes=(folder / "proving.key").stat().st_size))
    return specs


def schedule(specs, seed):
    rng = random.Random(seed)
    jobs = []
    for repeat in range(1, REPETITIONS + 1):
        indices = list(range(len(specs)))
        rng.shuffle(indices)
        for index in indices:
            jobs.append(dict(spec=index, repeat=repeat, order=len(jobs) + 1))
    return jobs


def summaries(specs, rows):
    result = []
    for spec in specs:
        base = {k:v for k,v in spec.items() if k != "source"}
        base.update(n=REPETITIONS, K=1, threads=rows[0]["threads"])
        for phase in ("witness", "prove", "verify"):
            group = [r for r in rows if r["family"] == spec["family"]
                     and r["activities"] == spec["activities"] and r["stage"] == phase]
            if len(group) != REPETITIONS or any(r["status"] != "ok" for r in group):
                raise ValueError("Incomplete or failed repetitions cannot become a final summary")
            for metric, label, divisor in (("operation_seconds", "seconds", 1),
                                          ("worker_seconds", "process_seconds", 1),
                                          ("process_peak_rss_bytes", "memory_mb", 1e6)):
                values = [r[metric] / divisor for r in group]
                for suffix, fn in (("mean", statistics.mean), ("sd", statistics.stdev),
                                   ("median", statistics.median), ("min", min), ("max", max)):
                    base[f"{phase}_{label}_{suffix}"] = fn(values)
        base["verified_proofs"] = sum(r.get("certified", 0) for r in rows
                                      if r["family"] == spec["family"] and r["activities"] == spec["activities"])
        result.append(base)
    return result


def run(source, output, binary, threads=14, seed=20261021, timeout=600):
    source, output, binary = [Path(p).resolve() for p in (source, output, binary)]
    if threads < 1 or timeout <= 0:
        raise ValueError("Threads and timeout must be positive")
    specs = read_specs(source)
    if not binary.is_file():
        raise FileNotFoundError(binary)
    output.mkdir(parents=True, exist_ok=True)
    required = sum((s["source"] / f).stat().st_size for s in specs for f in FILES)
    if shutil.disk_usage(output).free < required + 1024**3:
        raise RuntimeError("Insufficient space to copy artifacts with 1 GB headroom")
    run_dir = output / ("ten_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        + "_" + uuid.uuid4().hex[:8])
    run_dir.mkdir(mode=0o700)
    print(f"NEW OUTPUT DIRECTORY: {run_dir}", flush=True)
    print("Copying existing circuits and keys. No compilation or setup will run.", flush=True)
    rows, sources = [], {}
    try:
        saved_binary = run_dir / "zkalign-eval"
        shutil.copy2(binary, saved_binary)
        for spec in specs:
            target = run_dir / "work" / f"{spec['family']}-{spec['activities']}"
            target.mkdir(parents=True)
            for name in FILES + ("measurements/compile.json",):
                original = spec["source"] / name
                copy = target / ("original_compile.json" if name == "measurements/compile.json" else name)
                shutil.copy2(original, copy)
                sources[str(original)] = sha(original)
                if sha(copy) != sources[str(original)]:
                    raise RuntimeError(f"Input changed while copying: {original}")
        jobs = schedule(specs, seed)
        json_new(run_dir / "ten_manifest.json", dict(
            repetitions=REPETITIONS, threads=threads, seed=seed, schedule=jobs,
            source=str(source), source_sha256=sources, binary_sha256=sha(saved_binary),
            python=sys.version, platform=platform.platform(), cpu_count=os.cpu_count(),
            runner_sha256=sha(Path(__file__)),
            measurement_runner_sha256=sha(ROOT / "eval/measure_fresh_v2.py"),
            operation_time="internal operation timer; proving includes constraint solving, excludes loading and serialization",
            process_time="blocking wait4 launch-to-completion time; separate metric",
            memory="whole-process OS peak RSS; decimal MB = bytes / 1000000",
            protocol="Existing circuit and keys reused; ten randomized blocks; fresh process per stage; no discarded warmups or outliers"))
        with (run_dir / "ten_scalability_runs.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            stream.flush()
            for job in jobs:
                spec = specs[job["spec"]]
                folder = run_dir / "work" / f"{spec['family']}-{spec['activities']}"
                prefix = f"ten-repeat-{job['repeat']}"
                for phase in ("witness", "prove", "verify"):
                    print(f"[{job['order']}/{len(jobs)}] {folder.name} repeat {job['repeat']}/10 {phase}", flush=True)
                    measured = stage(saved_binary, folder, phase, case=folder / "private-0.json",
                                     prefix=prefix, tag=f"{prefix}-{phase}", threads=threads, timeout=timeout)
                    row = {k:v for k,v in spec.items() if k != "source"}
                    row.update({k:v for k,v in measured.items() if k in FIELDS and k not in spec})
                    row.update(repeat=job["repeat"], order=job["order"], stage=phase, threads=threads, K=1)
                    row.update({f"{k}_bytes":v for k,v in measured.get("bytes", {}).items()
                                if f"{k}_bytes" in FIELDS})
                    for key in ("operation_seconds", "worker_seconds", "process_peak_rss_bytes"):
                        if not isinstance(row.get(key), (float, int)) or not math.isfinite(row[key]) or row[key] <= 0:
                            row.update(status="error", error=f"Invalid {key}")
                    if phase == "verify":
                        row["certified"] = measured.get("details", {}).get("certified", 0)
                        if row["certified"] != 1:
                            row.update(status="error", error="Expected exactly one verified proof")
                    rows.append(row)
                    writer.writerow(row)
                    stream.flush()
                    if row.get("status") != "ok" or row.get("exit_code") != 0:
                        raise RuntimeError(f"Stage failed: {measured.get('measurement_file')}")
        for path, expected in sources.items():
            if sha(path) != expected:
                raise RuntimeError(f"Original input changed during run: {path}")
        summary = summaries(specs, rows)
        with (run_dir / "ten_model_scalability.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
        json_new(run_dir / "ten_complete.json", dict(status="ok", configurations=len(specs),
                 verified_proofs=sum(r["verified_proofs"] for r in summary), measurements=len(rows)))
    except BaseException as error:
        json_new(run_dir / "ten_failed.json", dict(error=str(error), measurements=len(rows)))
        print(f"Stopped. Partial results retained in {run_dir}", flush=True)
        raise
    print(f"Complete. Raw CSV: {run_dir / 'ten_scalability_runs.csv'}", flush=True)
    print(f"Summary CSV: {run_dir / 'ten_model_scalability.csv'}", flush=True)
    return run_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "outputs/evaluation/scalability")
    parser.add_argument("--output-parent", type=Path, default=ROOT / "outputs/scalability-ten")
    parser.add_argument("--binary", type=Path, default=ROOT / "build/zkalign-eval")
    parser.add_argument("--threads", type=int, default=14)
    parser.add_argument("--seed", type=int, default=20261021)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--check", action="store_true", help="Check inputs without writing or benchmarking")
    args = parser.parse_args()
    if args.check:
        specs = read_specs(args.source.resolve())
        if not args.binary.is_file():
            raise FileNotFoundError(args.binary)
        print(f"Ready: {len(specs)} saved configurations, 10 repetitions, 240 proofs. No benchmark started.")
        return
    run(args.source, args.output_parent, args.binary, args.threads, args.seed, args.timeout)


if __name__ == "__main__":
    main()
