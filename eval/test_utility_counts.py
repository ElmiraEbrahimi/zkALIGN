import tempfile
import unittest
from pathlib import Path

import matplotlib.pyplot as plt

from eval.plotting.utility_counts import DATASETS, generate, make_figure
from eval.run import csv_write


class UtilityCountFigureTests(unittest.TestCase):
    def test_percentages_use_each_population_and_labels_remain_counts(self):
        rows = self.rows()
        rows[0]["N"] = 210
        fig, ax = make_figure(rows, percent=True)
        self.assertEqual(ax.get_ylim()[0], 0)
        self.assertAlmostEqual(ax.containers[0][0].get_height(), 100 * 200 / 210)
        self.assertAlmostEqual(ax.containers[1][0].get_height(), 100 * 180 / 210)
        self.assertAlmostEqual(ax.containers[0][1].get_height(), 100 * 200 / 300)
        self.assertIn("200", [t.get_text() for t in ax.texts])
        self.assertIn("180", [t.get_text() for t in ax.texts])
        self.assertNotIn("$K$", [t.get_text() for t in ax.texts])
        plt.close(fig)

    def rows(self):
        return [
            dict(
                dataset=name,
                K=k,
                mode="groth16",
                N=300,
                processed=300,
                complete=True,
                errors=0,
                reference_qualified=200,
                certified=180,
                reference_share=200 / 300,
                certified_share=0.6,
            )
            for name in DATASETS
            for k in range(4)
        ]

    def test_independent_counts_single_axis_and_side_by_side_bars(self):
        fig, ax = make_figure(self.rows())
        self.assertEqual(len(fig.axes), 1)
        self.assertEqual(len(ax.containers), 2)
        for reference, certified in zip(*ax.containers):
            self.assertEqual(reference.get_height(), 200)
            self.assertEqual(certified.get_height(), 180)
            self.assertLess(
                reference.get_x() + reference.get_width(), certified.get_x()
            )
        self.assertAlmostEqual(fig.get_figwidth() * 2.54, 12.2)
        plt.close(fig)

    def test_export_preserves_old_figure_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "data/fig_utility.csv"
            csv_write(source, self.rows())
            original = source.read_bytes()
            (root / "figures").mkdir()
            old = root / "figures/fig_utility.pdf"
            old.write_bytes(b"old four-panel figure")
            csv_path, pdf_path = generate(source, root / "data", root / "figures")
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(old.read_bytes(), b"old four-panel figure")
            self.assertEqual(csv_path.name, "fig_utility_counts.csv")
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))
            previous_counts = pdf_path.read_bytes()
            percent_csv, percent_pdf = generate(
                source, root / "data", root / "figures", percent=True
            )
            self.assertEqual(percent_csv.name, "fig_utility_percent.csv")
            self.assertTrue(percent_pdf.read_bytes().startswith(b"%PDF"))
            self.assertEqual(pdf_path.read_bytes(), previous_counts)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
