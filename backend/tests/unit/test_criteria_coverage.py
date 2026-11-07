import unittest

from app.analysis.criteria_coverage import case_coverage, relevant_intervals
from app.reference.pfd_criteria import load_criteria


def case(segments, bands, notice_type="G", center=2_250_000_000, width=2_000_000):
    return {
        "case_id": "c1",
        "space": {"notice_type": notice_type},
        "finnish_usage": {"center_hz": center, "bandwidth_hz": width,
                          "frequency_min_hz": center - width // 2, "frequency_max_hz": center + width // 2},
        "matched_frequency_segments_hz": [{"frequency_min_hz": a, "frequency_max_hz": b} for a, b in segments],
        "space_frequency_bands": [{"frequency_min_hz": a, "frequency_max_hz": b} for a, b in bands],
    }


class CoverageTests(unittest.TestCase):
    def test_wide_satellite_band_is_judged_at_the_finnish_frequency_only(self):
        # Satellite band spans 1.6-2.3 GHz; the Finnish band at 1.8 GHz has no Table 21-4 row.
        wide = case([(1_799_000_000, 1_801_000_000)], [(1_600_000_000, 2_300_000_000)], center=1_800_000_000)
        self.assertEqual(case_coverage(wide, load_criteria())["coverage"], "no_criterion")

    def test_co_frequency_case_in_shared_band_gets_limit(self):
        inside = case([(2_249_000_000, 2_251_000_000)], [(2_200_000_000, 2_290_000_000)], notice_type="N")
        result = case_coverage(inside, load_criteria())
        self.assertEqual(result["criterion_ids"], ["T21-4-1525-2300-METSAT-SR-SO-EESS"])
        self.assertEqual(result["orbit"], "non_gso")

    def test_adjacent_case_is_clipped_to_one_bandwidth_guard(self):
        adjacent = case([], [(2_251_500_000, 2_400_000_000)])
        self.assertEqual(relevant_intervals(adjacent), [(2_251_500_000, 2_253_000_000)])


if __name__ == "__main__":
    unittest.main()
