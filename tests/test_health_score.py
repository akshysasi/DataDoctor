import unittest

import pandas as pd

from analyzer import analyze_dataset


class HealthScoreTests(unittest.TestCase):
    def test_clean_dataset_scores_excellent_with_full_breakdown(self):
        report = analyze_dataset(pd.DataFrame({"value": [1, 2, 3, 4]}))
        score = report["health_score"]
        self.assertEqual(score["score"], 100)
        self.assertEqual(score["band"], "excellent")
        self.assertEqual(score["available_weight"], 100)
        self.assertEqual(
            {key: value["weight"] for key, value in score["components"].items()},
            {"completeness": 35, "duplicates": 25, "outliers": 25, "constant_columns": 15},
        )

    def test_issue_rates_drive_component_scores(self):
        report = analyze_dataset(pd.DataFrame({
            "value": [1, 1, 1, 1, 100, None],
            "label": ["a", "a", "b", "c", "d", "e"],
        }))
        score = report["health_score"]
        self.assertEqual(score["components"]["completeness"]["score"], 91.67)
        self.assertEqual(score["components"]["duplicates"]["score"], 83.33)
        self.assertEqual(score["components"]["constant_columns"]["score"], 100)
        self.assertIsInstance(score["score"], int)
        self.assertGreaterEqual(score["score"], 0)
        self.assertLessEqual(score["score"], 100)

    def test_non_numeric_data_marks_outliers_unavailable_and_normalizes(self):
        report = analyze_dataset(pd.DataFrame({"label": ["a", "b", "c"]}))
        score = report["health_score"]
        self.assertFalse(score["components"]["outliers"]["available"])
        self.assertEqual(score["available_weight"], 75)
        self.assertEqual(score["score"], 100)

    def test_empty_dataset_has_no_score(self):
        report = analyze_dataset(pd.DataFrame({"value": pd.Series(dtype="float64")}))
        score = report["health_score"]
        self.assertIsNone(score["score"])
        self.assertEqual(score["band"], "unavailable")
        self.assertEqual(score["available_weight"], 0)
        self.assertTrue(all(not part["available"] for part in score["components"].values()))

    def test_existing_report_fields_remain_available(self):
        report = analyze_dataset(pd.DataFrame({"value": [1, 2, None, 4]}))
        for key in ("rows", "columns", "missing_values", "duplicate_rows", "data_types",
                    "constant_columns", "potential_outliers", "summary", "correlations", "suggestions"):
            self.assertIn(key, report)


if __name__ == "__main__":
    unittest.main()
