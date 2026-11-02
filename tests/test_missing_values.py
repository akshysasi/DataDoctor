import io
import unittest

import pandas as pd

from analyzer import fill_missing_values
from app import app, _active_datasets


class MissingValueCleanerTests(unittest.TestCase):
    def test_numeric_mean_and_median_and_text_mode(self):
        source = pd.DataFrame({
            "number": [1.0, 3.0, None, None],
            "category": ["red", "red", "blue", None],
            "all_missing": [None, None, None, None],
        })

        median = fill_missing_values(source, "median")
        mean = fill_missing_values(source, "mean")

        self.assertEqual(median["number"].tolist(), [1.0, 3.0, 2.0, 2.0])
        self.assertEqual(mean["number"].tolist(), [1.0, 3.0, 2.0, 2.0])
        self.assertEqual(median["category"].tolist(), ["red", "red", "blue", "red"])
        self.assertTrue(median["all_missing"].isna().all())
        self.assertTrue(source.isna().sum().sum() > median.isna().sum().sum())

    def test_mean_and_median_differ_and_invalid_strategy_is_rejected(self):
        source = pd.DataFrame({"number": [1.0, 2.0, 100.0, None]})
        self.assertEqual(fill_missing_values(source, "mean")["number"].iloc[-1], 34.333333333333336)
        self.assertEqual(fill_missing_values(source, "median")["number"].iloc[-1], 2.0)
        with self.assertRaises(ValueError):
            fill_missing_values(source, "mode")

    def test_preview_apply_undo_for_missing_values(self):
        app.config.update(TESTING=True)
        client = app.test_client()
        _active_datasets.clear()
        client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(b"name,value\nA,1\nB,\nC,3\nD,\n"), "gaps.csv"),
        }, content_type="multipart/form-data")
        state = next(iter(_active_datasets.values()))

        preview = client.post("/", data={"action": "preview_missing", "numeric_strategy": "mean"})
        html = preview.get_data(as_text=True)
        self.assertIn("2 → 0 MISSING CELLS", html)
        self.assertEqual(int(state["current"].isna().sum().sum()), 2)

        applied = client.post("/", data={"action": "apply_missing", "numeric_strategy": "mean"})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(state["current"]["value"].tolist(), [1.0, 2.0, 3.0, 2.0])
        self.assertTrue(state["original"].isna().sum().sum() == 2)

        undone = client.post("/", data={"action": "undo_operation"})
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(int(state["current"].isna().sum().sum()), 2)


if __name__ == "__main__":
    unittest.main()
