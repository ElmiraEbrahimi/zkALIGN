"""Controlled fixed-shape circuits. Synthetic models are not rediscovered."""

import argparse
import copy
import json
import secrets
import os
import sys
import platform
import subprocess
import psutil
from pathlib import Path
from eval.data import FIELD, ROOT, save
from eval.measure import stage, run_worker
from eval.run import BINARY, initialize, require, csv_write


def synthetic(family, n, sigma=128, gamma=256):
    labels = []
    edges = []
    moves = []
    events = []

    def transition(label, pre, post):
        labels.append(label)
        edges.append((pre, post))
        return len(labels)

    def fire(t):
        label = labels[t - 1]
        moves.append({"type": 1 if label else 3, "activity": label, "transition": t})
        if label:
            events.append(label)

    if family in ("sequence", "loop"):
        places = n + 1
        initial = [1] + [0] * n
        final = [0] * n + [1]
        for i in range(n):
            transition(i + 1, [i], [i + 1])
        for t in range(1, n + 1):
            fire(t)
        if family == "loop":
            fire(transition(0, [n], [0]))
            for t in range(1, n + 1):
                fire(t)
    elif family == "choice":
        places = 2
        initial = [1, 0]
        final = [0, 1]
        for i in range(n):
            transition(i + 1, [0], [1])
        fire(1)
    elif family == "parallel":
        places = 2 * n + 2
        initial = [1] + [0] * (places - 1)
        final = [0] * (places - 1) + [1]
        split = transition(0, [0], list(range(1, n + 1)))
        for i in range(n):
            transition(i + 1, [i + 1], [n + i + 1])
        join = transition(0, list(range(n + 1, 2 * n + 1)), [places - 1])
        fire(split)
        for t in range(n + 1, 1, -1):
            fire(t)
        fire(join)
    else:
        raise ValueError(family)
    cfg = {
        "activity_count": n,
        "trace_capacity": sigma,
        "alignment_capacity": gamma,
        "initial": initial,
        "final": final,
        "labels": labels,
        "model_costs": [int(a != 0) for a in labels],
        "inputs": [
            [j for j, (pre, _) in enumerate(edges) if p in pre] for p in range(places)
        ],
        "outputs": [
            [j for j, (_, post) in enumerate(edges) if p in post] for p in range(places)
        ],
    }
    assert len(events) <= sigma and len(moves) <= gamma
    case = {
        "case_id": family,
        "index": 0,
        "events": events,
        "moves": moves,
        "cost": 0,
        "salt": str(secrets.randbelow(FIELD)),
        "status": "aligned",
        "alignment_seconds": 0,
    }
    return cfg, case


def replay(cfg, case):
    m = cfg["initial"][:]
    events = []
    cost = 0
    for row in case["moves"]:
        t = row["transition"] - 1
        if row["type"] == 1:
            assert row["activity"] == cfg["labels"][t] and row["activity"] != 0
            events.append(row["activity"])
        pre = [int(t in v) for v in cfg["inputs"]]
        post = [int(t in v) for v in cfg["outputs"]]
        assert all(x >= y for x, y in zip(m, pre))
        m = [x - y + z for x, y, z in zip(m, pre, post)]
        assert all(x in (0, 1) for x in m)
        if row["type"] == 3:
            cost += cfg["model_costs"][t]
    assert m == cfg["final"] and events == case["events"] and cost == case["cost"]


def experiment(folder, cfg, cases, repeat=3):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "config.json").exists():
        if json.loads((folder / "config.json").read_text()) != cfg:
            raise ValueError("use a new folder for changed configuration")
    else:
        save(folder / "config.json", cfg)
        save(folder / "cases.json", cases)
    initialize(folder)
    require(stage(BINARY, folder, "context", tag="context"))
    records = []
    for i in range(repeat):
        for phase in ("witness", "prove", "verify"):
            r = stage(
                BINARY,
                folder,
                phase,
                case=folder / "private-0.json",
                prefix="k1-0",
                tag=f"repeat-{i}-{phase}",
            )
            require(r)
            records.append(
                {
                    "repeat": i,
                    "stage": phase,
                    **{k: v for k, v in r.items() if not isinstance(v, (dict, list))},
                }
            )
    return records


def models(root, sizes=(5, 10, 20, 30, 40, 50), repeat=3):
    rows = []
    for family in ("sequence", "choice", "parallel", "loop"):
        for n in sizes:
            folder = Path(root) / "scalability" / f"{family}-{n}"
            cfg, c = synthetic(family, n)
            replay(cfg, c)
            measurements = experiment(folder, cfg, [c], repeat)
            compile = json.loads((folder / "measurements/compile.json").read_text())
            setup = json.loads((folder / "measurements/setup.json").read_text())
            for m in measurements:
                rows.append(
                    {
                        "family": family,
                        "activities": n,
                        "places": len(cfg["initial"]),
                        "transitions": len(cfg["labels"]),
                        "arcs": sum(map(len, cfg["inputs"] + cfg["outputs"])),
                        "trace_capacity": 128,
                        "alignment_capacity": 256,
                        "constraints": compile["constraints"],
                        "pk_bytes": setup["bytes"]["pk"],
                        **m,
                    }
                )
            csv_write(Path(root) / "results/scal_model.csv", rows)
            print("model", family, n, "complete", flush=True)


def capacities(root, bounds=(32, 64, 128, 256, 384), repeat=3):
    source = Path(root) / "data/sepsis"
    cfg = json.loads((source / "config.json").read_text())
    cases = json.loads((source / "cases.json").read_text())
    selected = copy.deepcopy(next(c for c in cases if c["case_id"] == "AG"))
    selected["index"] = 0
    rows = []
    for bound in bounds:
        config = copy.deepcopy(cfg)
        config["alignment_capacity"] = bound
        folder = Path(root) / "capacity" / str(bound)
        measurements = experiment(folder, config, [selected], repeat)
        compile = json.loads((folder / "measurements/compile.json").read_text())
        setup = json.loads((folder / "measurements/setup.json").read_text())
        for m in measurements:
            rows.append(
                {
                    "alignment_capacity": bound,
                    "trace_capacity": cfg["trace_capacity"],
                    "N": len(cases),
                    "fit": sum(
                        c["status"] == "aligned" and len(c["moves"]) <= bound
                        for c in cases
                    ),
                    "constraints": compile["constraints"],
                    "setup_seconds": setup["operation_seconds"],
                    "pk_bytes": setup["bytes"]["pk"],
                    **m,
                }
            )
        csv_write(Path(root) / "results/scal_capacity.csv", rows)
        print("capacity", bound, "complete", flush=True)


def repeats(root, repeat=5):
    save(
        Path(root) / "results/performance_environment.json",
        {
            "platform": platform.platform(),
            "python": sys.version,
            "ram_bytes": psutil.virtual_memory().total,
            "cpus": os.cpu_count(),
            "cpu_model": (
                subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
                ).strip()
                if sys.platform == "darwin"
                else platform.processor()
            ),
            "git_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "go_modules": subprocess.check_output(
                ["go", "list", "-m", "all"], cwd=ROOT, text=True
            ).splitlines(),
            "python_packages": subprocess.check_output(
                [sys.executable, "-m", "pip", "freeze"], text=True
            ).splitlines(),
            "cache_note": "Fresh processes; operating-system filesystem caches are not flushed.",
        },
    )
    rows = []
    for name in ("bpic13cp", "rtfm", "hospital", "sepsis"):
        folder = Path(root) / "data" / name
        cases = json.loads((folder / "cases.json").read_text())
        eligible = sorted(
            [c for c in cases if c["cost"] is not None and c["cost"] <= 1],
            key=lambda c: len(c["moves"]),
        )
        chosen = {
            eligible[i]["index"] for i in (0, len(eligible) // 2, len(eligible) - 1)
        }
        if name == "sepsis":
            chosen.update(c["index"] for c in eligible if c["case_id"] in ("AG", "NGA"))
        for threads in (1, None):
            for index in sorted(chosen):
                for i in range(repeat):
                    if threads is None:
                        result = (
                            folder
                            / "measurements"
                            / f"timing-alignment-{index}-{i}.json"
                        )
                        r = run_worker(
                            [
                                sys.executable,
                                "-m",
                                "eval.alignment_bench",
                                "--folder",
                                str(folder),
                                "--index",
                                str(index),
                                "--result",
                                str(result),
                            ],
                            result,
                        )
                        require(r)
                        rows.append(
                            {
                                "dataset": name,
                                "index": index,
                                "repeat": i,
                                "threads": "default",
                                "stage": "alignment",
                                **{
                                    k: v
                                    for k, v in r.items()
                                    if not isinstance(v, (dict, list))
                                },
                            }
                        )
                    for phase in ("witness", "prove", "verify"):
                        tag = f"timing-{threads}-{index}-{i}-{phase}"
                        r = stage(
                            BINARY,
                            folder,
                            phase,
                            case=folder / f"private-{index}.json",
                            prefix=f"k1-{index}",
                            tag=tag,
                            threads=threads,
                        )
                        require(r)
                        rows.append(
                            {
                                "dataset": name,
                                "index": index,
                                "repeat": i,
                                "threads": threads or "default",
                                "stage": phase,
                                **{
                                    k: v
                                    for k, v in r.items()
                                    if not isinstance(v, (dict, list))
                                },
                            }
                        )
                    csv_write(Path(root) / "results/repeated_timings.csv", rows)
        print("timing repeats", name, "complete", flush=True)


def setup_repeats(root, repeat=5):
    rows = []
    for name in ("bpic13cp", "rtfm", "hospital", "sepsis"):
        cfg = json.loads((Path(root) / "data" / name / "config.json").read_text())
        for i in range(repeat):
            folder = Path(root) / "setup-repeats" / name / str(i)
            save(folder / "config.json", cfg)
            for phase in ("compile", "setup"):
                r = stage(BINARY, folder, phase, tag=phase)
                require(r)
                rows.append(
                    {
                        "dataset": name,
                        "repeat": i,
                        "stage": phase,
                        **{
                            k: v
                            for k, v in r.items()
                            if not isinstance(v, (dict, list))
                        },
                        **r.get("bytes", {}),
                    }
                )
            csv_write(Path(root) / "results/repeated_setup.csv", rows)
        print("setup repeats", name, "complete", flush=True)


def population(root, repeat=3):
    rows = []
    for n in (100, 1000, 10000, 100000):
        for i in range(repeat):
            result = Path(root) / "population" / f"root-{n}-{i}.json"
            r = run_worker(
                [
                    str(BINARY),
                    "-stage",
                    "population-root",
                    "-population",
                    str(n),
                    "-result",
                    str(result),
                ],
                result,
            )
            require(r)
            rows.append(
                {
                    "N": n,
                    "repeat": i,
                    "mode": "synthetic_roster_only",
                    "distinct_proofs_verified": 0,
                    **{k: v for k, v in r.items() if not isinstance(v, (dict, list))},
                }
            )
            csv_write(Path(root) / "results/scal_population.csv", rows)


def integrity_all(root):
    rows = []
    for name in ("bpic13cp", "rtfm", "hospital", "sepsis"):
        folder = Path(root) / "data" / name
        r = stage(BINARY, folder, "integrity", tag="integrity", timeout=1800)
        for row in r.get("details", []):
            rows.append({"dataset": name, **row})
        csv_write(Path(root) / "results/integrity.csv", rows)
        require(r)
        print("integrity", name, "complete", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    p.add_argument(
        "--mode",
        choices=[
            "models",
            "capacity",
            "repeats",
            "setup-repeats",
            "population",
            "integrity",
        ],
        required=True,
    )
    p.add_argument("--repeat", type=int)
    p.add_argument("--sizes", type=int, nargs="+", default=[5, 10, 20, 30, 40, 50])
    a = p.parse_args()
    if a.mode == "models":
        models(a.root, a.sizes, a.repeat or 3)
    elif a.mode == "capacity":
        capacities(a.root, repeat=a.repeat or 3)
    elif a.mode == "repeats":
        repeats(a.root, a.repeat or 5)
    elif a.mode == "population":
        population(a.root, a.repeat or 3)
    elif a.mode == "setup-repeats":
        setup_repeats(a.root, a.repeat or 5)
    else:
        integrity_all(a.root)
