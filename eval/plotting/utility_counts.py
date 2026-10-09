"""Alternative utility figure: side-by-side counts, no overlapping series.

Read saved Groth16 utility data only. Keep the four-panel plot and its data intact.
"""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from eval.plotting.utility import DATASETS, ROOT, plot_rows

LABELS = {
    "bpic13cp": "BPI 2013",
    "rtfm": "Road Traffic Fines",
    "sepsis": "Sepsis",
    "hospital": "Hospital Billing",
}
RED, BLUE = "#8c2d26", "#2171b5"


@plt.rc_context(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 8,
        "axes.linewidth": 0.6,
        "pdf.fonttype": 42,
    }
)
def make_figure(rows, percent=False):
    fig, ax = plt.subplots(figsize=(12.2 / 2.54, 5.2 / 2.54))
    x = np.array([5 * DATASETS.index(r["dataset"]) + int(r["K"]) for r in rows])
    reference = np.array([int(r["reference_qualified"]) for r in rows])
    certified = np.array([int(r["certified"]) for r in rows])
    population = np.array([int(r["N"]) for r in rows])
    reference_height = 100 * reference / population if percent else reference
    certified_height = 100 * certified / population if percent else certified
    # Both series come from their own counts, even when the observed values agree.
    ax.bar(
        x - 0.19,
        reference_height,
        width=0.34,
        color=RED,
        edgecolor=RED,
        linewidth=0.3,
        label="Plaintext (PM4Py)",
    )
    ax.bar(
        x + 0.19,
        certified_height,
        width=0.34,
        color=BLUE,
        edgecolor=BLUE,
        linewidth=0.3,
        label="zkALIGN",
    )
    for center, a, b, a_height, b_height in zip(
        x, reference, certified, reference_height, certified_height
    ):
        if a == b:
            ax.text(
                center,
                a_height + (1.5 if percent else 5),
                str(a),
                ha="center",
                va="bottom",
                fontsize=6.5,
            )
        else:
            # Do not print a shared count if a future run contains a discrepancy.
            ax.annotate(
                str(a),
                (center - 0.19, a_height),
                xytext=(-2, 4),
                textcoords="offset points",
                ha="right",
                fontsize=6.5,
                color=RED,
            )
            ax.annotate(
                str(b),
                (center + 0.19, b_height),
                xytext=(2, 4),
                textcoords="offset points",
                ha="left",
                fontsize=6.5,
                color=BLUE,
            )
    ax.set_xticks(x, [str(r["K"]) for r in rows])
    for name in DATASETS:
        group = [r for r in rows if r["dataset"] == name]
        ax.text(
            5 * DATASETS.index(name) + 1.5,
            -0.17,
            LABELS[name] + "\n" + rf"$N={int(group[0]['N'])}$",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=7.5,
        )
    ax.set_ylabel(r"Cases within $K$ (%)" if percent else "Number of cases")
    if not percent:
        ax.text(
            -0.08, -0.035, "$K$", transform=ax.transAxes, ha="right", va="top", fontsize=8
        )
    ax.set_xlim(-0.7, 18.7)
    if percent:
        # Bar heights always start at zero. Extra space above 100 is for labels.
        ax.set_ylim(0, 110)
        ax.set_yticks([0, 25, 50, 75, 100])
    else:
        upper = max(reference.max(), certified.max())
        ax.set_ylim(0, 50 * np.ceil((upper + 20) / 50))
        ax.set_yticks([0, 100, 200, 300])
    ax.grid(axis="y", linestyle="--", linewidth=0.4, alpha=0.35)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", length=2, pad=3)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.23),
        ncol=2,
        frameon=False,
        handlelength=1.4,
        columnspacing=1.5,
    )
    fig.subplots_adjust(left=0.115, right=0.99, bottom=0.27, top=0.83)
    return fig, ax


def generate(source, data, figures, percent=False):
    rows = plot_rows(source)
    data, figures = Path(data), Path(figures)
    data.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    stem = "fig_utility_percent" if percent else "fig_utility_counts"
    csv_path = data / (stem + ".csv")
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    # Render from the delivered figure-specific CSV, not a hidden source.
    fig, _ = make_figure(plot_rows(csv_path), percent=percent)
    pdf_path = figures / (stem + ".pdf")
    fig.savefig(pdf_path)
    plt.close(fig)
    return csv_path, pdf_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "eval/plotting/data/fig_utility.csv"
    )
    parser.add_argument("--data", type=Path, default=ROOT / "eval/plotting/data")
    parser.add_argument("--figures", type=Path, default=ROOT / "eval/results/figures")
    parser.add_argument(
        "--percent",
        action="store_true",
        help="Separate percentage-bar variant with exact counts above the pairs",
    )
    args = parser.parse_args()
    for path in generate(args.source, args.data, args.figures, percent=args.percent):
        print(path)


if __name__ == "__main__":
    main()
