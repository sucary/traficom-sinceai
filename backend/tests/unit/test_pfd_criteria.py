import math
import unittest

from app.reference.pfd_criteria import (
    criteria_for, criterion_by_id, evaluate_formula, formula_variables, limit_at, load_criteria,
)

ROUNDING_TOLERANCE_DB = 0.01
KNOWN_SOURCE_STEPS = {
    ("T21-4-1518-1525-MSS-USA-71W-125W", 4),
    ("T21-4-9900-10400-EESS-ACTIVE", 5.7),
    ("T21-4-9900-10400-EESS-ACTIVE", 53),
}


def value(criterion_id, d, **parameters):
    return limit_at(criterion_by_id(criterion_id), d, **parameters)["value_db"]


class StructureTests(unittest.TestCase):
    document = load_criteria()

    def test_ids_unique_and_sources_cited(self):
        ids = [item["criterion_id"] for item in self.document["criteria"]]
        self.assertEqual(len(ids), len(set(ids)))
        for criterion in self.document["criteria"]:
            self.assertIn(criterion["source"], self.document["sources"])
            self.assertTrue(criterion["location"]["printed_page"] and criterion["location"]["pdf_page"])
            self.assertIn(criterion["orbit"], {"gso", "non_gso", "any"})
            self.assertIn(criterion["reference_bandwidth_hz"], {4000, 1_000_000, 1_500_000})

    def test_segments_cover_0_to_90_without_gaps(self):
        for criterion in self.document["criteria"]:
            segments = criterion["segments"]
            self.assertEqual(segments[0]["elev_min_deg"], 0, criterion["criterion_id"])
            self.assertEqual(segments[-1]["elev_max_deg"], 90, criterion["criterion_id"])
            for left, right in zip(segments, segments[1:]):
                self.assertEqual(left["elev_max_deg"], right["elev_min_deg"], criterion["criterion_id"])
                self.assertLess(left["elev_min_deg"], left["elev_max_deg"])

    def test_special_methods_tagged(self):
        tagged = {c["criterion_id"]: c["special_method"]["method"] for c in self.document["criteria"] if "special_method" in c}
        self.assertEqual(tagged, {"T21-4-9900-10400-EESS-ACTIVE": "mean_pfd_sar",
                                  "T21-4-27.5-30-ISS-NGSO": "resolution_679_annex_2"})

    def test_bands_are_valid(self):
        for criterion in self.document["criteria"]:
            for band in criterion["bands"]:
                self.assertLess(band["frequency_min_hz"], band["frequency_max_hz"])
                if not band["applies_in_finland"]:
                    self.assertTrue(band.get("finland_note"), criterion["criterion_id"])

    def test_references_resolve_and_formulas_use_declared_parameters(self):
        for criterion in self.document["criteria"]:
            for footnote in criterion["footnotes"]:
                self.assertIn(footnote, self.document["footnotes"])
            for condition in criterion["conditions"]:
                self.assertIn(condition, self.document["conditions"])
            used = set().union(*(formula_variables(item["formula"]) for item in criterion["segments"])) - {"d"}
            self.assertEqual(used, set(criterion["parameters"]), criterion["criterion_id"])

    def test_limits_continuous_at_boundaries_except_printed_rounding(self):
        for criterion in self.document["criteria"]:
            segments = criterion["segments"]
            for left, right in zip(segments, segments[1:]):
                angle = left["elev_max_deg"]
                for parameter in (0, 10):
                    a = evaluate_formula(left["formula"], angle, X=parameter, Y=parameter)
                    b = evaluate_formula(right["formula"], angle, X=parameter, Y=parameter)
                    if (criterion["criterion_id"], angle) in KNOWN_SOURCE_STEPS:
                        self.assertLess(abs(a - b), 0.5)
                    else:
                        self.assertAlmostEqual(a, b, delta=ROUNDING_TOLERANCE_DB,
                                               msg=f'{criterion["criterion_id"]} at {angle}')


class KnownValueTests(unittest.TestCase):
    def test_3400_4200_gso_example_quoted_by_traficom(self):
        self.assertEqual(value("T21-4-3400-4200-FSS-GSO", 3), -152)
        self.assertEqual(value("T21-4-3400-4200-FSS-GSO", 15), -147)
        self.assertEqual(value("T21-4-3400-4200-FSS-GSO", 60), -142)
        self.assertEqual(criterion_by_id("T21-4-3400-4200-FSS-GSO")["reference_bandwidth_hz"], 4000)

    def test_piecewise_rows(self):
        self.assertAlmostEqual(value("T21-4-13.4-13.65-FSS-GSO", 10), -155)
        self.assertAlmostEqual(value("T21-4-13.4-13.65-FSS-GSO", 82), -150)
        self.assertAlmostEqual(value("T21-4-2500-2690-FSS-BSS-RDSS-MSS", 15), -130.5)
        self.assertAlmostEqual(value("T21-4-37.5-40-FSS-MSS-GSO", 11), -119)
        self.assertAlmostEqual(value("T21-4-40.5-42-FSS-BSS-GSO", 20), -107.5)
        self.assertAlmostEqual(value("T21-4-9900-10400-EESS-ACTIVE", 15), -109 + 25)
        self.assertAlmostEqual(value("T21-4-1670-1700-EESS-METSAT", 45), -133)

    def test_parameterised_rows(self):
        result = limit_at(criterion_by_id("T21-4-3400-4200-FSS-NGSO"), 15)
        self.assertIsNone(result["value_db"])
        self.assertEqual(result["missing_parameters"], ["Y"])
        self.assertAlmostEqual(value("T21-4-3400-4200-FSS-NGSO", 15, Y=0), -132)
        self.assertAlmostEqual(value("T21-4-17.7-19.3-FSS-NGSO-X", 3, X=10), -125)
        self.assertAlmostEqual(value("T21-4-17.7-19.3-FSS-NGSO-X", 60, X=10), -105)

    def test_boundary_belongs_to_lower_segment(self):
        segment = limit_at(criterion_by_id("T21-4-3400-4200-FSS-GSO"), 5)["segment"]
        self.assertEqual((segment["elev_min_deg"], segment["elev_max_deg"]), (0, 5))

    def test_out_of_range_angle_rejected(self):
        with self.assertRaises(ValueError):
            limit_at(criterion_by_id("T21-4-3400-4200-FSS-GSO"), 91)


class LookupTests(unittest.TestCase):
    def ids(self, *args, **kwargs):
        return {item.get("criterion_id") for item in criteria_for(*args, **kwargs)}

    def test_orbit_filter(self):
        self.assertEqual(self.ids(3_700_000_000, 3_736_000_000, "gso"), {"T21-4-3400-4200-FSS-GSO"})
        self.assertEqual(self.ids(3_700_000_000, 3_736_000_000, "non_gso"), {"T21-4-3400-4200-FSS-NGSO"})
        self.assertEqual(len(self.ids(3_700_000_000, 3_736_000_000)), 2)

    def test_region_and_footnote_rows_excluded_for_finland(self):
        self.assertEqual(self.ids(12_600_000_000, 12_700_000_000, "gso"), {None})
        self.assertIn("T21-4-12.2-12.75-FSS-GSO", self.ids(12_600_000_000, 12_700_000_000, "gso", finland_only=False))
        self.assertEqual(self.ids(1_520_000_000, 1_524_000_000), {None})

    def test_no_criterion_is_explicit(self):
        result = criteria_for(1_545_000_000, 1_555_000_000, "gso")
        self.assertEqual(result[0]["status"], "no_criterion")

    def test_emission_touching_band_edge_is_not_in_band(self):
        self.assertEqual(self.ids(2_483_500_000, 2_500_000_000, "gso"), {None})
        self.assertEqual(self.ids(2_500_000_000, 2_500_000_000, "gso"), {None})
        self.assertIn("T21-4-2500-2690-FSS-BSS-RDSS-MSS", self.ids(2_499_000_000, 2_501_000_000, "gso"))

    def test_partial_overlap_reported(self):
        result = criteria_for(4_100_000_000, 4_300_000_000, "gso")
        self.assertEqual([(item["criterion_id"], item["overlap"]) for item in result],
                         [("T21-4-3400-4200-FSS-GSO", "partial")])


class EvaluatorSafetyTests(unittest.TestCase):
    def test_rejects_non_arithmetic_syntax(self):
        for formula in ("__import__('os')", "d.real", "[d]", "d ** 2", "log10(d, 2)", "open('x')"):
            with self.assertRaises(ValueError, msg=formula):
                evaluate_formula(formula, 10)

    def test_log10(self):
        self.assertAlmostEqual(evaluate_formula("-193.0 + 20*log10(d)", 10), -173.0)
        self.assertTrue(math.isclose(evaluate_formula("-(4/3)*(d - 5)", 8), -4.0))


if __name__ == "__main__":
    unittest.main()
