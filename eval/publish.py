"""Publish compact research results only after checking experiment completeness."""

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from eval.data import ROOT, DATASETS, save
from eval.validate import validate
from eval.report import report

PUBLISHED_FILES = {
    "README.md",
    "environment.json",
    "performance_environment.json",
    "utility_environment.json",
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
        for row in summary:
            if row.get("dataset") == name and row["mode"] == "groth16":
                k = row["K"]
                audit = json.loads(
                    (folder / f"measurements/audit-k{k}.json").read_text()
                )["details"]
                save(destination / "audit-reports" / f"{name}-k{k}.json", audit)
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


def publish_utility(root, destination):
    """Refresh utility evidence only, without plots or performance experiments."""
    from eval.plotting.utility import plot_rows

    root, destination = Path(root), Path(destination)
    validate(root)
    results = root / "results"
    summary = plot_rows(results / "utility_summary.csv")
    audits = {}
    last_audit = 0
    # Check the saved evidence, not just the aggregate counts. This does not
    # regenerate proofs or claim that parsing a receipt is fresh verification.
    for name in DATASETS:
        folder = root / "data" / name
        rows = json.loads((folder / "utility.json").read_text())
        for row in rows:
            if not row["certified"]:
                continue
            prefix = f"k{row['K']}-{row['index']}"
            if not (folder / (prefix + ".proof.json")).is_file():
                raise ValueError(f"Missing proof artifact: {name}/{prefix}")
            for phase in ("witness", "prove", "verify"):
                record = json.loads(
                    (folder / "measurements" / f"{phase}-{prefix}.json").read_text()
                )
                if record["status"] != "ok":
                    raise ValueError(f"Failed {phase}: {name}/{prefix}")
        for k in range(4):
            path = folder / f"measurements/audit-k{k}.json"
            record = json.loads(path.read_text())
            audit = record["details"]
            expected = {
                f"k{k}-{r['index']}.proof.json"
                for r in rows
                if r["K"] == k and r["certified"]
            }
            receipts = audit["receipts"]
            if (
                record["status"] != "ok"
                or any(r["status"] != "accepted" for r in receipts)
                or len(receipts) != len(expected)
                or {r["file"] for r in receipts} != expected
            ):
                raise ValueError(f"Inconsistent audit receipts: {name}/K={k}")
            audits[f"{name}-k{k}.json"] = audit
            last_audit = max(last_audit, record["end_ns"])
    destination.mkdir(parents=True, exist_ok=True)
    for filename in (
        "utility_cases.csv",
        "utility_summary.csv",
        "utility_environment.json",
    ):
        (destination / filename).write_text((results / filename).read_text())
    for filename, audit in audits.items():
        save(destination / "audit-reports" / filename, audit)
        if filename.endswith("-k1.json"):
            save(destination / "audit-reports" / filename.replace("-k1", ""), audit)
    provenance_path = destination / "provenance.json"
    provenance = (
        json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    )
    provenance.update(
        real_proof_thresholds=[0, 1, 2, 3],
        solver_only_thresholds=[],
        utility_source_revision=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        utility_last_audit_utc=datetime.fromtimestamp(
            last_audit / 1e9, timezone.utc
        ).isoformat(),
        utility_case_threshold_results=sum(int(r["processed"]) for r in summary),
        utility_verified_proofs=sum(int(r["certified"]) for r in summary),
        utility_above_threshold_policy="No proof attempted; retained as uncertified.",
        utility_evidence="Saved successful witness/prove/verify records, proof files, and audit receipts checked.",
        private_artifacts_included=False,
    )
    save(provenance_path, provenance)
    readme = destination / "README.md"
    old = readme.read_text() if readme.exists() else "# Evaluation results\n"
    # Preserve the independently measured performance sections verbatim.
    lines = [
        line
        for line in old.splitlines()
        if not any(line.startswith(f"- {name}, K=") for name in DATASETS)
    ]
    start, end = "<!-- utility-results:start -->", "<!-- utility-results:end -->"
    text = "\n".join(lines)
    if start in text and end in text:
        before, rest = text.split(start, 1)
        text = before + rest.split(end, 1)[1]
    block = [
        start,
        "## Utility preservation",
        "",
        f"All four thresholds use real Groth16 proofs. Verified proofs: {provenance['utility_verified_proofs']:,}.",
        "Only reference-qualified cases are proved. Above-threshold cases remain uncertified without a proof attempt.",
        "Thus utility measures successful certification coverage, not adversarial rejection or universal soundness.",
        "The earlier interrupted run log is historical; completed per-case records and all 16 audit reports are the evidence.",
        "Source: utility_summary.csv, utility_cases.csv, and audit-reports/<dataset>-k<K>.json.",
        "",
    ]
    for r in summary:
        block.append(
            f"- {r['dataset']}, K={r['K']}: reference-qualified {r['reference_qualified']}, "
            f"certified {r['certified']}/{r['N']}, errors {r['errors']}, capacity misses {r['missed_capacity']}."
        )
    block.extend([end, ""])
    readme.write_text(text.rstrip() + "\n\n" + "\n".join(block))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    parser.add_argument("--destination", type=Path, default=ROOT / "eval/results")
    parser.add_argument(
        "--utility-only",
        action="store_true",
        help="Publish completed utility evidence only; no plots or performance refresh",
    )
    args = parser.parse_args()
    action = publish_utility if args.utility_only else publish
    print(action(args.root, args.destination))
