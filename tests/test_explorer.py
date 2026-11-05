import io
import unittest

import pandas as pd
from unittest.mock import patch

from app import app, _active_datasets


class ExplorerRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        _active_datasets.clear()
        self.client = app.test_client()

    def upload(self, content=b"name,score\nA,1\nB,2\nA,3\nC,4\n"):
        return self.client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(content), "explorer.csv"),
        }, content_type="multipart/form-data")

    def test_search_pagination_and_missing_highlight_payload(self):
        self.upload(b"name,score\nA,1\nB,\nA,3\nC,4\n")
        response = self.client.get("/api/explorer?q=B&page=1&page_size=10")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["total_rows"], 1)
        self.assertEqual(payload["rows"][0]["cells"][0]["value"], "B")
        self.assertTrue(payload["rows"][0]["cells"][1]["missing"])

    def test_explorer_paginates_large_row_sets(self):
        rows = "name,score\n" + "".join(f"row-{index},{index}\n" for index in range(12))
        self.upload(rows.encode())
        first = self.client.get("/api/explorer?page=1&page_size=10").get_json()
        second = self.client.get("/api/explorer?page=2&page_size=10").get_json()
        self.assertEqual((first["pages"], len(first["rows"])), (2, 10))
        self.assertEqual((second["page"], len(second["rows"])), (2, 2))

    def test_anomaly_model_runs_only_for_review_and_reuses_cached_result(self):
        self.upload()
        state = next(iter(_active_datasets.values()))
        mask = pd.Series([False, True, False, False])
        scores = pd.Series([0.1, 0.9, 0.2, 0.3])
        with patch("app.detect_anomalies", return_value=(mask, scores, None)) as detector:
            self.client.get("/")
            self.assertEqual(detector.call_count, 0)
            self.client.post("/", data={"action": "preview_anomalies"})
            self.client.get("/")
            self.assertEqual(detector.call_count, 1)
            self.assertEqual(sum(state["anomaly_cache"]["mask"]), 1)

    def test_empty_csv_renders_a_recoverable_error(self):
        response = self.upload(b"")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Could not analyze that CSV", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
