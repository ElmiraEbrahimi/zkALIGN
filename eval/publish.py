"""Publish compact research results only after checking experiment completeness."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
import pandas as pd
from eval.data import ROOT, DATASETS, save
from eval.validate import validate
from eval.report import report

PUBLISHED_FILES = {
    "README.md",
    "environment.json",
    "performance_environment.json",
    "evaluation_results.tex",
    "evaluation_tables.tex",
    "evaluation_figures.tex",
    "artifact_sizes.csv",
    "datasets.csv",
    "integrity.csv",
    "measurements.csv",
    "overhead.csv",
    "overhead_summary.csv",
    "performance_summary.csv",
    "repeated_setup.csv",
    "repeated_timings.csv",
    "scal_capacity.csv",
    "scal_length.csv",
    "scal_length_repeated.csv",
    "scal_model.csv",
    "scal_model_summary.csv",
    "scal_population.csv",
    "scal_population_proofs.csv",
    "setup_summary.csv",
    "thread_scaling.csv",
    "uncertified_cases.csv",
    "utility_cases.csv",
    "utility_summary.csv",
}


def check_experiments(root):
    results = Path(root) / "results"

    def read(name):
        frame = pd.read_csv(results / name)
        if frame.empty:
            raise ValueError(f"empty experiment: {name}")
        if "status" in frame and not frame.status.eq("ok").all():
            raise ValueError(f"unsuccessful measurements: {name}")
        return frame

    timings = read("repeated_timings.csv")
    if set(timings.dataset) != set(DATASETS):
        raise ValueError("missing dataset timings")
    for _, group in timings.groupby(["dataset", "threads", "index", "stage"]):
        if sorted(group["repeat"]) != list(range(5)):
            raise ValueError("incomplete five-repeat timing group")
    for name, group in timings.groupby("dataset"):
        if set(group.threads.astype(str)) != {"1", "default"}:
            raise ValueError(f"missing thread setting: {name}")
        for _, g in group.groupby(["threads", "index"]):
            if not {"witness", "prove", "verify"} <= set(g.stage):
                raise ValueError("missing measured stage")
    setup = read("repeated_setup.csv")
    if len(setup) != 40 or set(setup.dataset) != set(DATASETS):
        raise ValueError("incomplete repeated setup")
    for _, group in setup.groupby(["dataset", "stage"]):
        if sorted(group["repeat"]) != list(range(5)):
            raise ValueError("incomplete setup repetitions")
    models = read("scal_model.csv")
    if len(models.groupby(["family", "activities"])) != 24 or len(models) != 216:
        raise ValueError("incomplete controlled-model study")
    capacity = read("scal_capacity.csv")
    if (
        set(capacity.alignment_capacity) != {32, 64, 128, 256, 384}
        or len(capacity) != 45
    ):
        raise ValueError("incomplete capacity study")
    roster = read("scal_population.csv")
    if set(roster.N) != {100, 1000, 10000, 100000} or len(roster) != 12:
        raise ValueError("incomplete root-reconstruction study")
    proofs = read("scal_population_proofs.csv")
    if (
        set(proofs.N) != {100, 300}
        or not proofs["mode"].eq("real_distinct_certificates").all()
    ):
        raise ValueError("incomplete distinct-proof population study")
    integrity = read("integrity.csv")
    if set(integrity.dataset) != set(DATASETS) or integrity.unexpected.sum() != 0:
        raise ValueError("incomplete or failed integrity study")


def publish(root, destination):
    root, destination = Path(root), Path(destination)
    summary = validate(root)
    check_experiments(root)
    report(root)
    destination.mkdir(parents=True, exist_ok=True)
    results = root / "results"
    for p in sorted(results.iterdir()):
        if p.is_file() and p.name in PUBLISHED_FILES:
            if p.suffix == ".csv":
                (destination / p.name).write_text(p.read_text())
            else:
                shutil.copy2(p, destination / p.name)
    for p in sorted((results / "figures").glob("*.pdf")):
        target = destination / "figures" / p.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    # One reproducible numerical input for each plotted figure, no private witnesses.
    from eval.plotting.draw import DRAW

    for name in DRAW:
        p = root / "plotting/data" / (name + ".csv")
        if p.exists():
            target = destination.parent / "plotting/data" / p.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
    # Public-data research metadata only. Never publish salts, witnesses, or keys.
    for name in DATASETS:
        folder = root / "data" / name
        for filename in (
            "config.json",
            "metadata.json",
            "split.json",
            "model.pnml",
            "model.ptml",
        ):
            p = folder / filename
            if p.exists():
                target = destination / "models" / name / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
        audit = json.loads((folder / "measurements/audit-k1.json").read_text())[
            "details"
        ]
        save(destination / "audit-reports" / (name + ".json"), audit)
    save(
        destination / "provenance.json",
        {
            "source_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "measurement_root": str(root),
            "scope": "Research outputs on fixed held-out cohorts, not full source-log certification.",
            "private_artifacts_included": False,
            "real_proof_thresholds": sorted(
                {r["K"] for r in summary if r["mode"] == "groth16"}
            ),
            "solver_only_thresholds": sorted(
                {r["K"] for r in summary if r["mode"] == "solver"}
            ),
        },
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    parser.add_argument("--destination", type=Path, default=ROOT / "eval/results")
    args = parser.parse_args()
    print(publish(args.root, args.destination))
