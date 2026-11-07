import unittest

from app.analysis.run_issues import plan


class RunIssuesTests(unittest.TestCase):
    def test_file_name_selects_pipeline(self):
        kind, issue, inputs = plan("ific3074.mdb")
        self.assertEqual((kind, issue, inputs[0]), ("space", 3074, "ific3074.mdb"))
        kind, issue, inputs = plan("brific3076.mdb")
        self.assertEqual((kind, issue), ("terrestrial", 3076))
        self.assertEqual(inputs[:2], ("brific3075.mdb", "brific3076.mdb"))

    def test_other_files_rejected(self):
        for name in ("SPS_ALL_IFIC3083.mdb", "30B_3083.mdb", "ific3074.zip", "notes.xlsx"):
            with self.assertRaises(ValueError, msg=name):
                plan(name)


if __name__ == "__main__":
    unittest.main()
