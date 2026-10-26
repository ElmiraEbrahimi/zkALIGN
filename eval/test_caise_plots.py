"""Regression checks for the compact, saved-data-only figure exports."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from eval.plotting.caise import generate
from eval.plotting.capacity_performance import draw as capacity
from eval.plotting.capacity_operation import make_figure as operation_capacity
from eval.plotting.draw import models, plt
from eval.plotting.plaintext_comparison import draw as comparison
from eval.plotting.utility_counts import ROOT, make_figure, plot_rows


DATA = ROOT / "eval/plotting/data"


def snapshot(fig):
    """Record data, error bars, labels and fonts independently of figure size."""
    axes = []
    for ax in fig.axes:
        axes.append((
            ax.get_xscale(), ax.get_yscale(), ax.get_xlim(), ax.get_ylim(),
            ax.get_xlabel(), ax.get_ylabel(),
            ax.xaxis.label.get_fontsize(), ax.yaxis.label.get_fontsize(),
            [(t.get_text(), t.get_fontsize()) for t in ax.texts],
            [(p.get_x(), p.get_width(), p.get_height(), p.get_facecolor())
             for p in ax.patches],
            [(np.asarray(line.get_xdata()).tolist(),
              np.asarray(line.get_ydata()).tolist()) for line in ax.lines],
            [[segment.tolist() for segment in c.get_segments()]
             for c in ax.collections if hasattr(c, "get_segments")],
        ))
    return axes


class CompactFigureTests(unittest.TestCase):
    def test_compact_utility_preserves_values_and_fonts(self):
        rows = plot_rows(DATA / "fig_utility.csv")
        original, _ = make_figure(rows, percent=True)
        compact, _ = make_figure(rows, percent=True, height_cm=4.5)
        self.assertEqual(snapshot(original), snapshot(compact))
        np.testing.assert_allclose(compact.get_size_inches() * 2.54, [12.2, 4.5])
        plt.close(original)
        plt.close(compact)

    def test_other_compact_figures_preserve_values_errors_and_fonts(self):
        for name, draw in (("plaintext_comparison", comparison),
                           ("capacity_performance", capacity),
                           ("model_scalability", models)):
            with self.subTest(name=name):
                frame = pd.read_csv(DATA / f"fig_{name}.csv")
                captured = []
                def capture(fig, *args, **kwargs):
                    captured.append(snapshot(fig))
                with patch.object(Figure, "savefig", capture):
                    draw(frame, Path("unused.pdf"))
                    draw(frame, Path("unused.pdf"), height_cm=4.5)
                self.assertEqual(captured[0], captured[1])

    def test_export_names_dimensions_and_read_only_sources(self):
        sources = list(DATA.glob("fig_*.csv"))
        before = {path: path.read_bytes() for path in sources}
        saved = []
        def capture(fig, path, *args, **kwargs):
            np.testing.assert_allclose(fig.get_size_inches() * 2.54, [12.2, 4.5])
            expected = {
                "caise_utility_percent.pdf": [[0, 25, 50, 75, 100]],
                "caise_plaintext_comparison.pdf": [[.001, .01, .1, 1]],
                "caise_capacity_performance.pdf": [[.01, .1, 1, 10], [0, 500, 1000, 1500, 2000]],
                "caise_model_scalability.pdf": [None, [.35, .40, .45, .50, .55]],
            }
            for ax, ticks in zip(fig.axes, expected[Path(path).name]):
                if ticks is not None:
                    np.testing.assert_allclose(ax.get_yticks(), ticks)
            saved.append(Path(path))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Figure, "savefig", capture):
                paths = generate(DATA, Path(tmp))
            self.assertEqual(paths, saved)
            self.assertEqual(len(paths), 4)
            self.assertTrue(all(p.name.startswith("caise_") for p in paths))
        self.assertEqual(before, {p: p.read_bytes() for p in sources})

    def test_operation_capacity_ticks_and_values(self):
        frame = pd.read_csv(DATA / "caise_capacity_operation_time.csv")
        fig, axes = operation_capacity(frame)
        self.assertEqual(axes[1].get_ylabel(), "Memory (MB)")
        self.assertIn("Witness encoding", axes[0].get_legend_handles_labels()[1])
        self.assertNotIn("Input-witness encoding", axes[0].get_legend_handles_labels()[1])
        for ax, panel in zip(axes, ("(a)", "(b)")):
            self.assertEqual([t.get_text() for t in ax.texts], [panel])
        self.assertEqual(axes[0].get_yscale(), "log")
        np.testing.assert_allclose(axes[0].get_yticks(), [.0001, .001, .01, .1, 1, 10])
        np.testing.assert_allclose(axes[1].get_yticks(), [0, 500, 1000, 1500, 2000])
        for container, stage in zip(axes[0].containers, ["compile", "setup", "witness", "prove"]):
            group = frame[frame.stage == stage].sort_values("alignment_capacity")
            np.testing.assert_allclose(np.asarray(container.lines[0].get_ydata(), dtype=float),
                                       group.operation_time_mean_s.to_numpy(dtype=float))
        plt.close(fig)

    def test_model_panel_labels(self):
        def capture(fig, *args, **kwargs):
            for ax, panel in zip(fig.axes, ("(a)", "(b)")):
                self.assertEqual([t.get_text() for t in ax.texts], [panel])
        with patch.object(Figure, "savefig", capture):
            models(pd.read_csv(DATA / "fig_model_scalability.csv"),
                   Path("unused.pdf"), height_cm=4.5)

if __name__ == "__main__":
    unittest.main()
