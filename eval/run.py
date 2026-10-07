"""Real proof runs with a fixed denominator and checkpointed per-case outcomes."""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import psutil
from pathlib import Path
from eval.data import ROOT, DATASETS, prepare, save
from eval.measure import stage

BINARY = ROOT / "build/zkalign-eval"


def csv_write(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    pending = path.with_name(path.name + ".pending")
    with pending.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(pending, path)


def require(result):
    if result["status"] != "ok":
        raise RuntimeError(result)


def initialize(folder):
    folder = Path(folder)
    frozen = {
        "config": json.loads((folder / "config.json").read_text()),
        "cases": json.loads((folder / "cases.json").read_text()),
    }
    lock = folder / "frozen-inputs.json"
    if lock.exists() and json.loads(lock.read_text()) != frozen:
        raise ValueError(
            "configuration or population changed; use a new output directory and setup"
        )
    if not lock.exists():
        save(lock, frozen)
    for name, artifact in [
        ("compile", "circuit.r1cs"),
        ("setup", "verification.key"),
        ("prepare", "population.json"),
    ]:
        if not (folder / artifact).exists():
            r = stage(BINARY, folder, name, tag=name)
            require(r)
    # Artifact existence alone is not sufficient evidence of successful setup.
    for name in ("compile", "setup"):
        r = json.loads((folder / "measurements" / (name + ".json")).read_text())
        require(r)


def evaluate(folder, thresholds=(1,), solve_thresholds=(0, 2, 3)):
    folder = Path(folder)
    initialize(folder)
    cases = json.loads((folder / "cases.json").read_text())
    name = folder.name
    rows = []
    cache = folder / "utility.json"
    old = json.loads(cache.read_text()) if cache.exists() else []
    done = {
        (r["index"], r["K"], r["mode"]): r
        for r in old
        if r["reason"]
        in (
            "certified",
            "above_threshold",
            "constraint_satisfied",
            "constraint_rejected",
            "capacity",
        )
    }
    for k in sorted(set(thresholds) | set(solve_thresholds)):
        full = k in thresholds
        require(stage(BINARY, folder, "context", k=k, tag=f"context-k{k}"))
        for c in cases:
            mode = "groth16" if full else "solver"
            key = (c["index"], k, mode)
            if key in done:
                rows.append(done[key])
                continue
            prefix = f"k{k}-{c['index']}"
            row = {
                "dataset": name,
                "index": c["index"],
                "case_id": c["case_id"],
                "K": k,
                "trace_length": len(c["events"]),
                "alignment_length": len(c["moves"]),
                "reference_cost": c["cost"],
                "reference_ok": c["cost"] is not None and c["cost"] <= k,
                "certified": False,
                "mode": mode,
                "alignment_seconds": c["alignment_seconds"],
            }
            if c["status"] != "aligned":
                row["reason"] = c["status"]
            else:
                cfg = json.loads((folder / "config.json").read_text())
                fits = (
                    len(c["events"]) <= cfg["trace_capacity"]
                    and len(c["moves"]) <= cfg["alignment_capacity"]
                )
                if not fits:
                    row["reason"] = "capacity"
                elif full and c["cost"] > k:
                    row["reason"] = "above_threshold"
                elif full:
                    row["reason"] = "certified"
                    for phase in ("witness", "prove", "verify"):
                        r = stage(
                            BINARY,
                            folder,
                            phase,
                            case=folder / f"private-{c['index']}.json",
                            k=k,
                            prefix=prefix,
                        )
                        row[phase + "_seconds"] = r.get("operation_seconds")
                        row[phase + "_peak_rss_bytes"] = r["process_peak_rss_bytes"]
                        row[phase + "_worker_seconds"] = r["worker_seconds"]
                        if r.get("bytes"):
                            for field, value in r["bytes"].items():
                                row[field + "_bytes"] = value
                        if r["status"] != "ok":
                            row["reason"] = phase + "_error"
                            row["error"] = r.get("error", "")
                            break
                    row["certified"] = row["reason"] == "certified"
                else:
                    r = stage(
                        BINARY,
                        folder,
                        "solve",
                        case=folder / f"private-{c['index']}.json",
                        k=k,
                        prefix=prefix,
                    )
                    solved = r["status"] == "ok"
                    row["solver_satisfied"] = solved
                    # An execution failure/timeout is not an expected unsatisfied constraint.
                    expected_rejection = r.get("error", "").startswith(
                        "constraint #"
                    ) or "constraint is not satisfied" in r.get("error", "")
                    row["reason"] = (
                        "constraint_satisfied"
                        if solved
                        else (
                            "constraint_rejected"
                            if expected_rejection
                            else "solver_error"
                        )
                    )
                    if (
                        solved != row["reference_ok"]
                        and row["reason"] != "solver_error"
                    ):
                        row["reason"] = "oracle_disagreement_error"
                    if row["reason"] == "solver_error":
                        row["error"] = r.get("error", "")
            rows.append(row)
            save(cache, rows)
            print(name, k, c["index"], row["reason"], flush=True)
        if full:
            r = stage(BINARY, folder, "audit", k=k, tag=f"audit-k{k}")
            require(r)
            counted = sum(
                rw["certified"]
                for rw in rows
                if rw["K"] == k and rw["mode"] == "groth16"
            )
            if r["details"]["certified"] != counted:
                raise RuntimeError("auditor count differs from recorded certificates")
    save(cache, rows)
    return rows


def collect(data, out):
    data = Path(data)
    out = Path(out)
    rows = []
    datasets = []
    measurements = []
    for folder in sorted(data.iterdir()):
        if not (folder / "metadata.json").exists():
            continue
        meta = json.loads((folder / "metadata.json").read_text())
        compile_file = folder / "measurements/compile.json"
        if compile_file.exists():
            meta["constraints"] = json.loads(compile_file.read_text()).get(
                "constraints"
            )
        datasets.append(meta)
        if (folder / "utility.json").exists():
            rows.extend(json.loads((folder / "utility.json").read_text()))
        for p in sorted((folder / "measurements").glob("*.json")):
            r = json.loads(p.read_text())
            measurements.append(
                {
                    "dataset": folder.name,
                    "measurement": p.stem,
                    **{k: v for k, v in r.items() if not isinstance(v, (dict, list))},
                    **r.get("bytes", {}),
                }
            )
    summary = []
    for name, k, mode in sorted(set((r["dataset"], r["K"], r["mode"]) for r in rows)):
        group = [
            r for r in rows if (r["dataset"], r["K"], r["mode"]) == (name, k, mode)
        ]
        total = next(d["population"] for d in datasets if d["dataset"] == name)
        population = json.loads((data / name / "cases.json").read_text())
        qualified = sum(c["cost"] is not None and c["cost"] <= k for c in population)
        summary.append(
            {
                "dataset": name,
                "K": k,
                "mode": mode,
                "N": total,
                "processed": len(group),
                "complete": len(group) == total,
                "reference_qualified": qualified,
                "certified": (
                    sum(r["certified"] for r in group) if mode == "groth16" else ""
                ),
                "false_certified": sum(
                    r["certified"] and not r["reference_ok"] for r in group
                ),
                "missed_capacity": sum(
                    r["reason"] == "capacity" and r["reference_ok"] for r in group
                ),
                "errors": sum(r["reason"].endswith("_error") for r in group),
                "reference_share": qualified / total,
                "certified_share": (
                    sum(r["certified"] for r in group) / total
                    if mode == "groth16"
                    else ""
                ),
            }
        )
    csv_write(out / "datasets.csv", datasets)
    csv_write(out / "utility_cases.csv", rows)
    csv_write(out / "utility_summary.csv", summary)
    csv_write(out / "measurements.csv", measurements)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--datasets", nargs="+", default=list(DATASETS))
    p.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    p.add_argument("--thresholds", type=int, nargs="+", default=[1])
    p.add_argument("--solve-thresholds", type=int, nargs="*", default=[0, 2, 3])
    p.add_argument("--collect-only", action="store_true")
    args = p.parse_args()
    out = args.root / "results"
    out.mkdir(parents=True, exist_ok=True)
    if not args.collect_only:
        subprocess.run(
            ["go", "build", "-o", str(BINARY), "./cmd/zkalign-eval"],
            cwd=ROOT,
            check=True,
        )
        save(
            out / "environment.json",
            {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "python": sys.version,
                "cpus": os.cpu_count(),
                "ram_bytes": psutil.virtual_memory().total,
                "cpu_model": (
                    subprocess.check_output(
                        ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
                    ).strip()
                    if sys.platform == "darwin"
                    else platform.processor()
                ),
                "go_modules": subprocess.check_output(
                    ["go", "list", "-m", "all"], cwd=ROOT, text=True
                ).splitlines(),
                "git": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "go": subprocess.check_output(["go", "version"], text=True).strip(),
                "dependencies": subprocess.check_output(
                    [sys.executable, "-m", "pip", "freeze"], text=True
                ).splitlines(),
                "measurement": "fresh process per stage; wait4 per-child RSS; 5ms samples",
            },
        )
        for name in args.datasets:
            prepare(name, args.root / "data")
            evaluate(args.root / "data" / name, args.thresholds, args.solve_thresholds)
            collect(args.root / "data", out)
    print(json.dumps(collect(args.root / "data", out), indent=2))


if __name__ == "__main__":
    main()
