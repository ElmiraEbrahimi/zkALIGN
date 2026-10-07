"""Fail closed before publishing evaluation claims."""

import argparse
import json
from pathlib import Path
from eval.data import ROOT, DATASETS
from eval.run import collect, initialize


def validate(root):
    root = Path(root)
    summary = collect(root / "data", root / "results")
    for name in DATASETS:
        folder = root / "data" / name
        initialize(folder)
        rows = json.loads((folder / "utility.json").read_text())
        real = [r for r in rows if r["K"] == 1 and r["mode"] == "groth16"]
        population = json.loads((folder / "cases.json").read_text())
        if len(real) != len(population):
            raise ValueError(f"{name}: incomplete real proof experiment")
        if len({r["index"] for r in real}) != len(population):
            raise ValueError("duplicate result indices")
        for r in rows:
            if r["reason"].endswith("_error"):
                raise ValueError(f"{name}: {r}")
            if r["mode"] == "groth16" and r["certified"] != r["reference_ok"]:
                raise ValueError(f"{name}: certification differs from reference")
            if r["mode"] == "solver" and r.get("solver_satisfied") != r["reference_ok"]:
                raise ValueError(f"{name}: solver differs from reference")
        for k in (0, 1, 2, 3):
            if len([r for r in rows if r["K"] == k]) != len(population):
                raise ValueError(f"{name}: threshold {k} incomplete")
        report = json.loads((folder / "measurements/audit-k1.json").read_text())[
            "details"
        ]
        if report["population"] != len(population) or report["certified"] != sum(
            r["certified"] for r in real
        ):
            raise ValueError("auditor report inconsistent with per-case results")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    print(json.dumps(validate(p.parse_args().root), indent=2))
