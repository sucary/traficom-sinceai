import unittest

from app.analysis.pipeline import SHARED_INPUTS, required_inputs, validate_counts


class PipelineValidationTests(unittest.TestCase):
    def test_matching_generation_is_accepted(self):
        checks = validate_counts(
            {"frequency_match_candidates": 20},
            {"raw_match_candidates": 20, "review_cases": 8},
            {"input_cases": 8, "future_calculation_queue": 6},
            {"input_cases": 6},
            {"counts": {"below_limit": 4, "missing_input": 2}},
        )
        self.assertTrue(all(item["matches"] for item in checks.values()))

    def test_mixed_generation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "matches_to_cases"):
            validate_counts(
                {"frequency_match_candidates": 10},
                {"raw_match_candidates": 20, "review_cases": 8},
                {"input_cases": 8, "future_calculation_queue": 6},
                {"input_cases": 6},
                {"counts": {"below_limit": 6}},
            )



class IssueSelectionTests(unittest.TestCase):
    def test_any_space_ific_issue_can_be_evaluated(self):
        self.assertEqual(required_inputs("ific3075.mdb"), ("ific3075.mdb", *SHARED_INPUTS))
        self.assertEqual(required_inputs()[0], "ific3074.mdb")

    def test_non_ific_files_are_rejected(self):
        for name in ("SPS_ALL_IFIC3083.mdb", "ific3075.zip", "../ific3075.mdb", "brific3076.mdb"):
            with self.assertRaises(ValueError, msg=name):
                required_inputs(name)


if __name__ == "__main__":
    unittest.main()
