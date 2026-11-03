import io
import unittest

import pandas as pd

from analyzer import outlier_columns_by_row, outlier_row_mask
from app import app, _active_datasets


class OutlierCleaningTests(unittest.TestCase):
    def test_iqr_mask_matches_reviewed_rows_and_column_names(self):
        frame = pd.DataFrame({
            "value": [1, 2, 3, 4, 100],
            "other": [10, 11, 12, 13, 500],
        })
        self.assertEqual(outlier_row_mask(frame).tolist(), [False, False, False, False, True])
        self.assertEqual(outlier_columns_by_row(frame)[-1], ["value", "other"])

    def test_preview_remove_and_undo_use_active_copy(self):
        app.config.update(TESTING=True)
        client = app.test_client()
        _active_datasets.clear()
        client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(b"label,value\na,1\nb,2\nc,3\nd,4\ne,100\n"), "outliers.csv"),
        }, content_type="multipart/form-data")
        state = next(iter(_active_datasets.values()))

        preview = client.post("/", data={"action": "preview_outliers"})
        html = preview.get_data(as_text=True)
        self.assertIn(">1</b> potential outlier rows", html)
        self.assertIn("Rows flagged by the IQR check", html)
        self.assertIn("100", html)
        self.assertEqual(len(state["current"]), 5)

        applied = client.post("/", data={"action": "apply_outliers"})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(state["current"]["value"].tolist(), [1, 2, 3, 4])
        self.assertEqual(len(state["original"]), 5)

        undone = client.post("/", data={"action": "undo_operation"})
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(state["current"]["value"].tolist(), [1, 2, 3, 4, 100])


if __name__ == "__main__":
    unittest.main()
