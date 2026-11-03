import io
import unittest

import pandas as pd

from analyzer import standardize_category_values
from app import app, _active_datasets


class CategoryStandardizationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        _active_datasets.clear()
        self.client = app.test_client()

    def test_trim_lower_title_and_missing_values(self):
        source = pd.DataFrame({
            "city": pd.Series(["  New YORK ", "los angeles", None], dtype="object")
        })
        lowered, lower_count = standardize_category_values(source, "city", "lower")
        titled, title_count = standardize_category_values(source, "city", "title")
        trimmed, trim_count = standardize_category_values(source, "city", "trim")

        self.assertEqual(lowered["city"].iloc[:2].tolist(), ["new york", "los angeles"])
        self.assertEqual(titled["city"].iloc[:2].tolist(), ["New York", "Los Angeles"])
        self.assertEqual(trimmed["city"].iloc[0], "New YORK")
        self.assertEqual([lower_count, title_count, trim_count], [1, 2, 1])
        self.assertTrue(pd.isna(lowered["city"].iloc[2]))
        self.assertEqual(source["city"].iloc[0], "  New YORK ")

    def test_preview_apply_and_undo(self):
        self.client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(
                b"city\n New York \nnew york\nNEW YORK\nLos Angeles\n"
            ), "cities.csv"),
        }, content_type="multipart/form-data")
        state = next(iter(_active_datasets.values()))

        preview = self.client.post("/", data={
            "action": "preview_standardize",
            "category_column": "city",
            "category_mode": "lower",
        })
        self.assertIn("3 value(s) will change", preview.get_data(as_text=True))
        self.assertEqual(state["current"]["city"].iloc[0], " New York ")

        applied = self.client.post("/", data={
            "action": "apply_standardize",
            "category_column": "city",
            "category_mode": "lower",
        })
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(state["current"]["city"].tolist(), ["new york", "new york", "new york", "los angeles"])

        self.client.post("/", data={"action": "undo_operation"})
        self.assertEqual(state["current"]["city"].iloc[0], " New York ")

    def test_numeric_column_cannot_be_standardized_as_category(self):
        source = pd.DataFrame({"score": [1, 2, 3]})
        with self.assertRaises(ValueError):
            standardize_category_values(source, "score", "lower")


if __name__ == "__main__":
    unittest.main()
