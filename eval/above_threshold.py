"""Complete negative utility evidence using saved R1CS, never Groth16 proving."""

import argparse
import csv
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from eval.data import ROOT, DATASETS, save
from eval.measure import stage


def read_csv(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def key(row):
    return row["dataset"], int(row["index"]), int(row["K"])


def classify(record):
    if record.get("stage") != "solve":
        raise ValueError("not a solver measurement")
    if record.get("status") == "ok" and record.get("exit_code") == 0:
        return True, "constraint_satisfied"
    if (record.get("status") == "error" and record.get("exit_code") == 1
            and re.match(r"^constraint #\d+ is not satisfied:", record.get("error", ""))):
        return False, "constraint_rejected"
    return "", "solver_error"


def enrich_summary(summary, cases, evidence):
    """Require complete, unique evidence. Errors are never counted as rejections."""
    expected = {key(r): r for r in cases
                if r["mode"] == "groth16" and int(r["reference_cost"]) > int(r["K"])}
    seen = set()
    counts, rejected = Counter(), Counter()
    for r in evidence:
        identity = key(r)
        if identity not in expected or identity in seen:
            raise ValueError(f"duplicate or unexpected solver evidence: {identity}")
        seen.add(identity)
        original = expected[identity]
        if (r["case_id"] != original["case_id"]
                or int(r["reference_cost"]) != int(original["reference_cost"])):
            raise ValueError(f"solver case mismatch: {identity}")
        flag = str(r["solver_satisfied"]).lower()
        reason = r["reason"]
        if ((reason == "constraint_rejected" and flag != "false")
                or (reason == "constraint_satisfied" and flag != "true")
                or reason not in ("constraint_rejected", "constraint_satisfied", "solver_error")):
            raise ValueError(f"inconsistent solver verdict: {identity}")
        group = (identity[0], identity[2])
        counts[group] += 1
        rejected[group] += reason == "constraint_rejected"
    if seen != set(expected):
        raise ValueError("incomplete above-threshold evidence")
    result = []
    for row in summary:
        group = (row["dataset"], int(row["K"]))
        if counts[group] != int(row["N"]) - int(row["reference_qualified"]):
            raise ValueError(f"above-threshold summary mismatch: {group}")
        result.append({**row, "above_threshold_cases": counts[group],
                       "above_threshold_rejected": rejected[group]})
    return result


def complete(root, destination, binary):
    # Import locally so collect() can reuse enrich_summary without an import cycle.
    from eval.run import csv_write

    root, destination = Path(root), Path(destination)
    results = root / "results"
    cases = read_csv(results / "utility_cases.csv")
    summary = read_csv(results / "utility_summary.csv")
    from eval.plotting.utility import plot_rows
    plot_rows(results / "utility_summary.csv")  # complete all-threshold Groth16 run
    negative = [r for r in cases if int(r["reference_cost"]) > int(r["K"])]
    if len({key(r) for r in negative}) != len(negative):
        raise ValueError("duplicate negative case-threshold pair")
    evidence, receipts = [], []
    reused = executed = 0
    for name in DATASETS:
        folder = root / "data" / name
        config = json.loads((folder / "config.json").read_text())
        population = json.loads((folder / "cases.json").read_text())
        frozen = json.loads((folder / "frozen-inputs.json").read_text())
        if frozen != {"config": config, "cases": population}:
            raise ValueError(f"frozen inputs changed: {name}")
        archive = folder / "utility-before-groth16.json"
        archived = json.loads(archive.read_text()) if archive.exists() else []
        old = {key(r): r for r in archived if r["mode"] == "solver"}
        for row in (r for r in negative if r["dataset"] == name):
            identity = key(row)
            _, index, k = identity
            case = next(c for c in population if c["index"] == index)
            private_path = folder / f"private-{index}.json"
            private = json.loads(private_path.read_text())
            for field in ("index", "case_id", "events", "moves", "cost", "salt", "status"):
                if private[field] != case[field]:
                    raise ValueError(f"private/frozen input mismatch: {identity}/{field}")
            if (row["case_id"] != case["case_id"] or int(row["reference_cost"]) != case["cost"]
                    or int(row["trace_length"]) != len(case["events"])
                    or int(row["alignment_length"]) != len(case["moves"])):
                raise ValueError(f"utility/frozen input mismatch: {identity}")
            previous = old.get(identity)
            path = folder / "measurements" / f"solve-k{k}-{index}.json"
            if previous is not None and path.exists():
                for field in ("case_id", "reference_cost", "trace_length", "alignment_length"):
                    if str(previous[field]) != str(row[field]):
                        raise ValueError(f"archived input mismatch: {identity}")
                record = json.loads(path.read_text())
                solved, reason = classify(record)
                if reason != previous["reason"] or solved != previous["solver_satisfied"]:
                    raise ValueError(f"archived receipt mismatch: {identity}")
                source = "archived_solver"
                reused += 1
            else:
                # Dedicated names preserve all earlier measurements and proof artifacts.
                tag = f"utility-above-threshold-k{k}-{index}"
                path = folder / "measurements" / (tag + ".json")
                if path.exists():
                    record = json.loads(path.read_text())
                    source = "saved_supplemental_solver"
                    reused += 1
                else:
                    record = stage(binary, folder, "solve", case=private_path, k=k, tag=tag)
                    source = "supplemental_solver"
                    executed += 1
                solved, reason = classify(record)
            item = {"dataset": name, "index": index, "case_id": case["case_id"],
                    "K": k, "reference_cost": case["cost"], "solver_satisfied": solved,
                    "reason": reason, "source": source,
                    "measurement": str(path.relative_to(root)), "error": record.get("error", "")}
            evidence.append(item)
            receipts.append({**item, "record": {f: v for f, v in record.items() if f != "measurement_file"}})
            if source == "supplemental_solver" or reason != "constraint_rejected":
                print(name, k, index, case["case_id"], reason, flush=True)
    enriched = enrich_summary(summary, cases, evidence)
    # Save anomalous outcomes too, then fail: never hide a satisfied witness or execution error.
    for out in {results, destination}:
        csv_write(out / "utility_above_threshold.csv", evidence)
        csv_write(out / "utility_summary.csv", enriched)
        save(out / "utility_above_threshold_receipts.json", receipts)
    if results.resolve() != destination.resolve():
        shutil.copy2(results / "utility_cases.csv", destination / "utility_cases.csv")
    report = {"reused": reused, "executed": executed, "total": len(evidence),
              "rejected": sum(r["reason"] == "constraint_rejected" for r in evidence),
              "exceptions": [r for r in evidence if r["reason"] != "constraint_rejected"]}
    print(json.dumps(report, indent=2))
    if report["exceptions"]:
        raise RuntimeError("unexpected solver outcomes saved; inspect utility_above_threshold.csv")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "outputs/evaluation")
    parser.add_argument("--destination", type=Path, default=ROOT / "eval/results")
    parser.add_argument("--binary", type=Path, default=ROOT / "build/zkalign-eval")
    args = parser.parse_args()
    complete(args.root, args.destination, args.binary)
