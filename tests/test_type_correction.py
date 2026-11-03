import io
import unittest

import pandas as pd

from analyzer import convert_column_type
from app import app, _active_datasets


class TypeCorrectionTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        _active_datasets.clear()
        self.client = app.test_client()

    def test_converts_valid_values_and_counts_unparseable_values(self):
        source = pd.DataFrame({
            "amount": pd.Series(["1.5", "bad", None], dtype="object"),
            "date": pd.Series(["2026-01-01", "2026-01-02", None], dtype="object"),
        })
        numeric, invalid_numbers = convert_column_type(source, "amount", "number")
        dates, invalid_dates = convert_column_type(source, "date", "date")

        self.assertEqual(invalid_numbers, 1)
        self.assertEqual(float(numeric["amount"].iloc[0]), 1.5)
        self.assertTrue(pd.isna(numeric["amount"].iloc[1]))
        self.assertEqual(invalid_dates, 0)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(dates["date"]))
        self.assertEqual(str(convert_column_type(source, "amount", "text")[0]["amount"].dtype), "string")
        self.assertEqual(source["amount"].iloc[1], "bad")

    def test_invalid_conversion_is_previewed_and_never_applied(self):
        self.client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(b"amount\n1.5\nbad\n"), "amounts.csv"),
        }, content_type="multipart/form-data")
        state = next(iter(_active_datasets.values()))
        before = state["current"].copy(deep=True)

        preview = self.client.post("/", data={
            "action": "preview_type", "type_column": "amount", "type_target": "number",
        })
        self.assertIn("1 INVALID VALUE(S)", preview.get_data(as_text=True))

        applied = self.client.post("/", data={
            "action": "apply_type", "type_column": "amount", "type_target": "number",
        })
        self.assertIn("Conversion stopped", applied.get_data(as_text=True))
        self.assertTrue(state["current"].equals(before))

    def test_valid_date_conversion_applies_and_can_be_undone(self):
        self.client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(b"event_date\n2026-01-01\n2026-01-02\n"), "dates.csv"),
        }, content_type="multipart/form-data")
        state = next(iter(_active_datasets.values()))
        self.client.post("/", data={
            "action": "apply_type", "type_column": "event_date", "type_target": "date",
        })
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(state["current"]["event_date"]))

        self.client.post("/", data={"action": "undo_operation"})
        self.assertEqual(state["current"]["event_date"].dtype, state["original"]["event_date"].dtype)


if __name__ == "__main__":
    unittest.main()
