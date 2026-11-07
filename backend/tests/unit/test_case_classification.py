import unittest

from app.analysis.case_classification import classify_case


def review_case(**space_changes):
    space = {
        "dataset_kind": "space_ific_evaluation", "notice_type": "G", "provision": "9.6",
        "action_code": "A", "publication_part": None, "status_code": "50",
    }
    space.update(space_changes)
    return {"space": space}


class ClassificationTests(unittest.TestCase):
    def test_cr_c_gso_case_is_eligible_without_interpreting_internal_status(self):
        result = classify_case(review_case())["regulatory_classification"]
        self.assertEqual(result["publication_family"], "coordination_request_cr_c")
        self.assertEqual(result["notice_object"], "geostationary_satellite_network")
        self.assertEqual(result["disposition"], "eligible_for_later_calculation")
        self.assertFalse(result["internal_status_interpreted"])

    def test_part_three_is_review_only(self):
        result = classify_case(review_case(provision="11.2", publication_part="3"))["regulatory_classification"]
        self.assertEqual(result["publication_stage"], "part_iii_returned_to_administration")
        self.assertEqual(result["disposition"], "returned_review_only")

    def test_reference_snapshot_is_context(self):
        result = classify_case(review_case(dataset_kind="ap30b_reference_snapshot"))["regulatory_classification"]
        self.assertEqual(result["dataset_role"], "reference_snapshot")
        self.assertEqual(result["disposition"], "reference_context")

    def test_unknown_public_code_is_not_guessed(self):
        result = classify_case(review_case(provision="mystery"))["regulatory_classification"]
        self.assertEqual(result["disposition"], "needs_information")
        self.assertIn("provision", result["unknown_public_codes"])


if __name__ == "__main__":
    unittest.main()
