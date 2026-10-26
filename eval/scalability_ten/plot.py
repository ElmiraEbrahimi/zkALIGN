"""Plot a completed ten-repeat run without changing any benchmark CSVs."""

import argparse
import csv
import json
import math
from pathlib import Path
import statistics

FAMILIES = ("sequence", "choice", "parallel", "loop")
SIZES = (5, 10, 20, 30, 40, 50)


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def validated_data(run):
    """Reconcile every plotted mean and sample SD with all ten raw timings."""
    complete = json.loads((run / "ten_complete.json").read_text())
    if any(complete.get(k) != v for k, v in {
        "status": "ok", "configurations": 24,
        "verified_proofs": 240, "measurements": 720,
    }.items()):
        raise ValueError("Expected a completed run with 240 verified proofs")
    raw = read_csv(run / "ten_scalability_runs.csv")
    summary = read_csv(run / "ten_model_scalability.csv")
    expected = {(f, s) for f in FAMILIES for s in SIZES}
    keyed = {(r["family"], int(r["activities"])): r for r in summary}
    if len(summary) != 24 or set(keyed) != expected or len(raw) != 720:
        raise ValueError("Missing or duplicated configurations/measurements")
    seen = set()
    for r in raw:
        key = (r["family"], int(r["activities"]), r["stage"], int(r["repeat"]))
        if (key in seen or key[:2] not in expected
                or key[2] not in ("witness", "prove", "verify")
                or key[3] not in range(1, 11)):
            raise ValueError("Unexpected or duplicate raw measurement")
        seen.add(key)
        if r["status"] != "ok" or int(r["exit_code"]) != 0:
            raise ValueError("Failed raw measurement")
        if r["stage"] == "verify" and float(r["certified"]) != 1:
            raise ValueError("A proof did not verify")
        for name, value in (("K", 1), ("trace_capacity", 128), ("alignment_capacity", 256)):
            if int(r[name]) != value:
                raise ValueError(f"Unexpected {name}")
        s = keyed[key[:2]]
        for name in ("constraints", "threads", "places", "transitions", "arcs", "pk_bytes"):
            if int(r[name]) != int(s[name]):
                raise ValueError(f"Raw/summary mismatch: {name}")
    result = []
    for family in FAMILIES:
        for size in SIZES:
            s = keyed[(family, size)]
            if int(s["n"]) != 10 or int(s["verified_proofs"]) != 10:
                raise ValueError("Each configuration must have ten verified proofs")
            values = [float(r["operation_seconds"]) for r in raw
                      if r["family"] == family and int(r["activities"]) == size
                      and r["stage"] == "prove"]
            if len(values) != 10 or any(not math.isfinite(v) or v <= 0 for v in values):
                raise ValueError("Invalid proof-operation timings")
            mean, sd = statistics.mean(values), statistics.stdev(values)
            if not (math.isclose(mean, float(s["prove_seconds_mean"]), rel_tol=1e-10)
                    and math.isclose(sd, float(s["prove_seconds_sd"]), rel_tol=1e-10)):
                raise ValueError("Summary disagrees with the raw proof timings")
            result.append(dict(family=family, activities=size,
                               constraints=int(s["constraints"]), mean=mean, sd=sd))
    return result


def draw(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator

    styles = {"sequence": ("#2171b5", "o", "-"),
              "choice": ("#8c2d26", "s", "--"),
              "parallel": ("#005a32", "^", "-."),
              "loop": ("#54278f", "D", ":")}
    with plt.rc_context({"font.family": "serif", "font.size": 8,
                         "font.serif": ["Times New Roman", "DejaVu Serif"],
                         "mathtext.fontset": "stix", "axes.linewidth": .7,
                         "pdf.fonttype": 42, "ps.fonttype": 42}):
        fig, axes = plt.subplots(1, 2, figsize=(12.2 / 2.54, 4.5 / 2.54))
        for family, (color, marker, linestyle) in styles.items():
            group = [r for r in rows if r["family"] == family]
            x = [r["activities"] for r in group]
            style = dict(color=color, marker=marker, linestyle=linestyle,
                         markersize=3, linewidth=.9, markerfacecolor="white",
                         label=family.capitalize())
            axes[0].plot(x, [r["constraints"] / 1000 for r in group], **style)
            axes[1].errorbar(x, [r["mean"] for r in group],
                             yerr=[r["sd"] for r in group], capsize=2,
                             elinewidth=.8, capthick=.8, **style)
        axes[0].set_ylabel(r"Constraints ($\times 10^3$)")
        axes[1].set_ylabel("Proof time (s)")
        axes[0].set_ylim(min(165, min(r["constraints"] / 1000 for r in rows) - 10),
                         max(300, max(r["constraints"] / 1000 for r in rows) + 10))
        # Include all error bars with margin, rather than clipping at the old limit.
        axes[1].set_ylim(min(.34, min(r["mean"] - r["sd"] for r in rows) - .01),
                         max(.56, max(r["mean"] + r["sd"] for r in rows) + .015))
        axes[1].yaxis.set_major_locator(MultipleLocator(.05))
        for ax, panel in zip(axes, ("(a)", "(b)")):
            ax.text(.04, 1.02, panel, transform=ax.transAxes,
                    ha="left", va="bottom", fontsize=9, clip_on=False)
            ax.set_xticks(SIZES)
            ax.set_xlim(2, 53)
            ax.grid(True, linestyle="--", linewidth=.4, alpha=.35)
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
        fig.supxlabel("Number of visible activities", fontsize=8.5, y=.035)
        fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center",
                   ncol=4, frameon=False, columnspacing=1.1, handlelength=1.4)
        fig.subplots_adjust(left=.12, right=.99, bottom=.266, top=.723, wspace=.42)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True,
                        help="Completed ten-run directory, not a CSV filename")
    args = parser.parse_args()
    run = args.run.resolve()
    rows = validated_data(run)
    output = run / "figures" / "caise_model_scalability-ten.pdf"
    draw(rows, output)
    print("Validated all 240 proofs and reconciled 24 means/sample SDs with raw timings.")
    print(f"PDF: {output}")


if __name__ == "__main__":
    main()
