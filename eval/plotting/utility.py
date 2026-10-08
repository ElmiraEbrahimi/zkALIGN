"""Export and plot the completed real-proof utility experiment only.

No evaluation workers are started. Source counts are preserved in the dedicated
CSV. Above-threshold cases are unproved, not cryptographic rejection attempts.
"""

import argparse
import csv
import math
from pathlib import Path

import pandas as pd

from eval.plotting.draw import utility

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("bpic13cp", "rtfm", "sepsis", "hospital")


def plot_rows(source):
    with Path(source).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = {(name, k) for name in DATASETS for k in range(4)}
    seen = set()
    populations = {}
    for row in rows:
        key = (row["dataset"], int(row["K"]))
        if key not in expected or key in seen:
            raise ValueError(f"Unexpected or duplicate utility row: {key}")
        seen.add(key)
        if row["mode"] != "groth16":
            raise ValueError(f"Real Groth16 results required: {key}")
        n = int(row["N"])
        if n <= 0 or int(row["processed"]) != n or row["complete"].lower() != "true":
            raise ValueError(f"Incomplete utility experiment: {key}")
        if int(row["errors"]) != 0:
            raise ValueError(f"Unresolved evaluation errors: {key}")
        previous = populations.setdefault(row["dataset"], n)
        if previous != n:
            raise ValueError(f"Population changed across thresholds: {key}")
        for count, share in (
            ("reference_qualified", "reference_share"),
            ("certified", "certified_share"),
        ):
            value = int(row[count])
            if not 0 <= value <= n or not math.isclose(
                float(row[share]), value / n, abs_tol=1e-12
            ):
                raise ValueError(f"Count/share mismatch: {key}/{count}")
        # Do not force the two series to agree: a genuine discrepancy must show.
        row["zk_share"] = float(row["certified_share"])
        row["reference_pct"] = 100 * int(row["reference_qualified"]) / n
        row["certified_pct"] = 100 * int(row["certified"]) / n
        row["zk_result_kind"] = "verified_certificate"
    if seen != expected:
        raise ValueError(f"Missing utility configurations: {sorted(expected - seen)}")
    return sorted(rows, key=lambda r: (DATASETS.index(r["dataset"]), int(r["K"])))


def generate(source, data, figures):
    rows = plot_rows(source)
    data, figures = Path(data), Path(figures)
    data.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    csv_path = data / "fig_utility.csv"
    pending = csv_path.with_suffix(".csv.pending")
    with pending.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    pending.replace(csv_path)
    pdf_path = figures / "fig_utility.pdf"
    utility(pd.read_csv(csv_path), pdf_path)
    return csv_path, pdf_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "outputs/evaluation/results/utility_summary.csv",
    )
    parser.add_argument("--data", type=Path, default=ROOT / "eval/plotting/data")
    parser.add_argument("--figures", type=Path, default=ROOT / "eval/results/figures")
    args = parser.parse_args()
    for path in generate(args.summary, args.data, args.figures):
        print(path)


if __name__ == "__main__":
    main()
