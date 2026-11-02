import io
import unittest

from app import app, _active_datasets


class DuplicateCleaningStudioTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        _active_datasets.clear()

    def upload(self):
        return self.client.post("/", data={
            "action": "analyze",
            "file": (io.BytesIO(b"name,value\nA,1\nB,2\nA,1\nA,3\n"), "people.csv"),
        }, content_type="multipart/form-data")

    def test_preview_shows_exact_duplicate_rows_without_changing_active_data(self):
        self.upload()
        response = self.client.post("/", data={"action": "preview_duplicates"})
        html = response.get_data(as_text=True)
        self.assertIn(">1</b> duplicate rows found", html)
        self.assertIn("Rows that will be removed", html)
        self.assertIn("PREVIEW ONLY", html)
        self.assertEqual(next(iter(_active_datasets.values()))["current"].shape[0], 4)

    def test_apply_undo_and_reset_operate_on_active_copy(self):
        original = self.upload()
        self.assertEqual(original.status_code, 200)
        state = next(iter(_active_datasets.values()))
        original_rows = state["original"].copy(deep=True)

        applied = self.client.post("/", data={"action": "apply_duplicates"})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(state["current"].shape[0], 3)
        self.assertIn(">0</b> duplicate rows found", applied.get_data(as_text=True))
        self.assertTrue(state["original"].equals(original_rows))

        undone = self.client.post("/", data={"action": "undo_duplicates"})
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(state["current"].shape[0], 4)

        self.client.post("/", data={"action": "apply_duplicates"})
        reset = self.client.post("/", data={"action": "reset_dataset"})
        self.assertEqual(reset.status_code, 200)
        self.assertTrue(state["current"].equals(original_rows))

    def test_duplicate_counter_and_preview_use_current_dataset(self):
        self.upload()
        self.client.post("/", data={"action": "apply_duplicates"})
        response = self.client.post("/", data={"action": "preview_duplicates"})
        html = response.get_data(as_text=True)
        self.assertIn(">0</b> duplicate rows found", html)
        self.assertIn("No duplicate rows to remove.", html)


if __name__ == "__main__":
    unittest.main()
