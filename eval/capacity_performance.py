"""Isolated, resumable capacity benchmarks; no utility or discovery rerun."""

import argparse
import copy
import fcntl
import json
import os
import platform
import shutil
import statistics
from pathlib import Path

from eval.data import ROOT, save
from eval.measure import stage
from eval.run import BINARY, csv_write, require


STAGES = ("compile", "setup", "witness", "prove", "verify")


def summarize(rows, repetitions):
    groups = {}
    for row in rows:
        if row["status"] == "ok":
            groups.setdefault((row["alignment_capacity"], row["stage"]), []).append(row)
    result = []
    for (bound, phase), group in sorted(groups.items()):
        row = {key: group[0][key] for key in (
            "dataset", "case_id", "K", "trace_capacity", "alignment_capacity",
            "constraints", "threads", "trace_length", "alignment_length")}
        row.update(stage=phase, n_repetitions=len(group), complete=len(group) == repetitions)
        for field, label, divisor in (
            ("operation_seconds", "time", 1),
            ("process_peak_rss_bytes", "mem", 1_000_000),
        ):
            values = [float(r[field]) / divisor for r in group]
            unit = "s" if label == "time" else "mb"
            row[f"{label}_mean_{unit}"] = statistics.mean(values)
            row[f"{label}_sd_{unit}"] = statistics.stdev(values) if len(values) > 1 else ""
        result.append(row)
    return result


def benchmark(source, output, binary=BINARY, bounds=(32, 64, 128, 256, 384),
              repetitions=5, threads=None):
    source, output, binary = Path(source), Path(output), Path(binary)
    if repetitions < 2 or not bounds or len(set(bounds)) != len(bounds):
        raise ValueError("Use at least two repeats and distinct capacity bounds")
    threads = threads or os.cpu_count() or 1
    if threads < 1:
        raise ValueError("threads must be positive")
    cfg = json.loads((source / "config.json").read_text())
    cases = json.loads((source / "cases.json").read_text())
    selected = copy.deepcopy(next(c for c in cases if c["case_id"] == "AG"))
    selected["index"] = 0
    if cfg["trace_capacity"] != 185:
        raise ValueError("This experiment requires Sepsis trace capacity 185")
    if selected["status"] != "aligned" or selected["cost"] > 1:
        raise ValueError("AG must have a valid alignment with cost at most K=1")
    if len(selected["events"]) > 185 or any(len(selected["moves"]) > b for b in bounds):
        raise ValueError("AG must fit every tested capacity")
    frozen = dict(config=cfg, case=selected, bounds=list(bounds), repetitions=repetitions,
                  threads=threads, K=1, platform=platform.platform(),
                  machine=platform.machine(), cpu_count=os.cpu_count())
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("A capacity benchmark is already running here") from exc
        manifest = output / "frozen-inputs.json"
        if manifest.exists() and json.loads(manifest.read_text()) != frozen:
            raise ValueError("Inputs or environment changed; choose a new --output folder")
        frozen_binary = output / "zkalign-eval"
        if frozen_binary.exists():
            if frozen_binary.read_bytes() != binary.read_bytes():
                raise ValueError("Benchmark binary changed; choose a new --output folder")
        else:
            shutil.copy2(binary, frozen_binary)
        save(manifest, frozen)
        rows = []

        def export():
            csv_write(output / "results/capacity_performance_runs.csv", rows)
            csv_write(output / "results/capacity_performance_summary.csv",
                      summarize(rows, repetitions))

        for bound in bounds:
            config = copy.deepcopy(cfg)
            config["alignment_capacity"] = bound
            for repeat in range(repetitions):
                folder = output / f"capacity-{bound}" / f"repeat-{repeat + 1}"
                done = folder / "complete.json"
                if done.exists():
                    cached = json.loads(done.read_text())
                    if len(cached) != len(STAGES) or any(r["status"] != "ok" for r in cached):
                        raise ValueError(f"Invalid completion record: {done}")
                    rows.extend(cached)
                    export()
                    print(f"capacity {bound}, repeat {repeat + 1}/{repetitions}: reused", flush=True)
                    continue
                save(folder / "config.json", config)
                save(folder / "cases.json", [selected])
                current = []
                constraints = None
                for phase in ("compile", "setup", "prepare", "context", "witness", "prove", "verify"):
                    print(f"capacity {bound}, repeat {repeat + 1}/{repetitions}: {phase}", flush=True)
                    measured = stage(frozen_binary, folder, phase,
                                     case=folder / "private-0.json", k=1, prefix="ag-k1",
                                     tag=phase, threads=threads)
                    if phase == "compile":
                        constraints = measured.get("constraints")
                    if phase in STAGES:
                        row = dict(dataset="sepsis", case_id="AG", K=1,
                                   trace_capacity=185, alignment_capacity=bound,
                                   trace_length=len(selected["events"]),
                                   alignment_length=len(selected["moves"]),
                                   constraints=constraints, threads=threads,
                                   repeat=repeat + 1, stage=phase,
                                   **{k: v for k, v in measured.items()
                                      if k not in ("stage", "constraints")
                                      and not isinstance(v, (dict, list))})
                        row.update({f"{k}_bytes": v for k, v in measured.get("bytes", {}).items()})
                        rows.append(row)
                        current.append(row)
                        export()
                    require(measured)
                save(done, current)
                print(f"capacity {bound}, repeat {repeat + 1}/{repetitions}: verified", flush=True)
        print(f"Complete. CSV files: {output / 'results'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "outputs/evaluation/data/sepsis")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/evaluation/capacity-performance")
    parser.add_argument("--binary", type=Path, default=BINARY)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--bounds", type=int, nargs="+", default=[32, 64, 128, 256, 384])
    args = parser.parse_args()
    benchmark(args.source.resolve(), args.output.resolve(), args.binary.resolve(),
              tuple(args.bounds), args.repeat, args.threads)
