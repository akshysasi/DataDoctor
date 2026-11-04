import io
import json
import unittest

from app import app, _active_datasets


class ExportCenterTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        _active_datasets.clear()
        self.client = app.test_client()
        self.client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(b"name,value\nA,1\nB,2\nA,1\n"), "sample.csv"),
        }, content_type="multipart/form-data")

    def test_quality_report_download_contains_active_analysis(self):
        response = self.client.post("/", data={"action": "download_report"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertIn("datadoctor_quality_report.json", response.headers["Content-Disposition"])

        report = json.loads(response.get_data(as_text=True))
        self.assertEqual(report["rows"], 3)
        self.assertEqual(report["duplicate_rows"], 1)
        self.assertIn("health_score", report)
        self.assertIn("summary", report)

    def test_report_tracks_cleaned_active_dataset(self):
        self.client.post("/", data={"action": "apply_duplicates"})
        response = self.client.post("/", data={"action": "download_report"})
        report = json.loads(response.get_data(as_text=True))
        self.assertEqual(report["rows"], 2)
        self.assertEqual(report["duplicate_rows"], 0)

    def test_export_center_exposes_csv_and_quality_report(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('id="export"', html)
        self.assertIn("Download active CSV", html)
        self.assertIn("Download quality report (JSON)", html)


if __name__ == "__main__":
    unittest.main()
