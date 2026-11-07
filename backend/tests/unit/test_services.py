import unittest

from app.reference.pfd_criteria import load_criteria
from app.reference.services import criterion_tokens, load_station_classes, service_match


class ServiceMappingTests(unittest.TestCase):
    def test_every_table_21_4_service_is_mapped(self):
        for criterion in load_criteria()["criteria"]:
            self.assertTrue(criterion_tokens(criterion), criterion["criterion_id"])

    def test_every_class_token_is_declared(self):
        document = load_station_classes()
        declared = set(document["service_tokens"])
        for code, entry in document["classes"].items():
            self.assertLessEqual(set(entry["tokens"]) | set(entry.get("ambiguous_for", [])), declared, code)

    def test_match_states(self):
        fss = frozenset({"FSS"})
        self.assertEqual(service_match(["EC"], fss), "match")
        self.assertEqual(service_match(["ER"], fss), "ambiguous")
        self.assertEqual(service_match(["EN"], fss), "no_match")
        self.assertEqual(service_match(["TC"], fss), "unknown")
        self.assertEqual(service_match(None, fss), "unknown")
        self.assertEqual(service_match(["EW"], frozenset({"EESS_ACTIVE"})), "ambiguous")
        self.assertEqual(service_match(["EJ"], frozenset({"MSS_EXCEPT_AERO"})), "no_match")


if __name__ == "__main__":
    unittest.main()
