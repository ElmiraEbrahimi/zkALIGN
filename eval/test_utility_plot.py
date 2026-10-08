import csv
import tempfile
import unittest
from pathlib import Path

from eval.plotting.utility import DATASETS, generate, plot_rows


class UtilityPlotTests(unittest.TestCase):
    def rows(self):
        return [
            dict(
                dataset=name,
                K=k,
                mode="groth16",
                N=10,
                processed=10,
                complete=True,
                errors=0,
                reference_qualified=8,
                certified=8,
                reference_share=0.8,
                certified_share=0.8,
            )
            for name in DATASETS
            for k in range(4)
        ]

    def write(self, path, rows):
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_exports_counts_and_percentages_and_only_utility_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "summary.csv"
            self.write(source, self.rows())
            original = source.read_bytes()
            csv_path, pdf_path = generate(source, root / "data", root / "figures")
            with csv_path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 16)
            self.assertTrue(all(float(r["certified_pct"]) == 80 for r in rows))
            self.assertTrue(all(r["mode"] == "groth16" for r in rows))
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))
            self.assertEqual(list((root / "figures").iterdir()), [pdf_path])
            self.assertEqual(source.read_bytes(), original)

    def test_rejects_incomplete_duplicate_solver_and_inconsistent_rows(self):
        changes = [
            lambda rows: rows.pop(),
            lambda rows: rows.append(rows[0].copy()),
            lambda rows: rows[0].update(mode="solver"),
            lambda rows: rows[0].update(processed=9),
            lambda rows: rows[0].update(errors=1),
            lambda rows: rows[0].update(certified_share=0.9),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "summary.csv"
            for change in changes:
                rows = self.rows()
                change(rows)
                self.write(source, rows)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    plot_rows(source)

    def test_disagreement_is_preserved_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "summary.csv"
            rows = self.rows()
            rows[0].update(certified=7, certified_share=0.7)
            self.write(source, rows)
            result = plot_rows(source)
            self.assertEqual(result[0]["reference_pct"], 80)
            self.assertEqual(result[0]["certified_pct"], 70)


if __name__ == "__main__":
    unittest.main()
