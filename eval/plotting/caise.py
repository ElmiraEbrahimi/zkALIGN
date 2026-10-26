"""Render compact CAiSE figures from saved CSVs without rerunning experiments.

Run from the repository root with:
    .venv/bin/python -m eval.plotting.caise

Existing fig_ PDFs and source CSVs are left untouched. Only the plot height
changes. Fonts, colors, values, axis scales, and standard deviations are retained.
"""

import argparse
from pathlib import Path

import pandas as pd

from .capacity_performance import draw as draw_capacity
from .draw import models, plt
from .plaintext_comparison import draw as draw_comparison
from .utility_counts import ROOT, make_figure, plot_rows


def generate(data, figures):
    data, figures = Path(data), Path(figures)
    height_cm = 4.5
    # Read every source before writing any output.
    rows = plot_rows(data / "fig_utility.csv")
    comparison = pd.read_csv(data / "fig_plaintext_comparison.csv")
    capacity = pd.read_csv(data / "fig_capacity_performance.csv")
    scalability = pd.read_csv(data / "fig_model_scalability.csv")
    figures.mkdir(parents=True, exist_ok=True)
    paths = [
        figures / "caise_utility_percent.pdf",
        figures / "caise_plaintext_comparison.pdf",
        figures / "caise_capacity_performance.pdf",
        figures / "caise_model_scalability.pdf",
    ]
    fig, _ = make_figure(rows, percent=True, height_cm=height_cm)
    fig.savefig(paths[0])
    plt.close(fig)
    draw_comparison(comparison, paths[1], height_cm=height_cm)
    draw_capacity(capacity, paths[2], height_cm=height_cm)
    models(scalability, paths[3], height_cm=height_cm)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "eval/plotting/data")
    parser.add_argument("--figures", type=Path, default=ROOT / "eval/results/figures")
    args = parser.parse_args()
    for path in generate(args.data, args.figures):
        print(path)


if __name__ == "__main__":
    main()
