import unittest

from app.analysis.case_consolidation import consolidate, merge_closed_intervals, notice_rollups


def candidate(source_row, lower, upper, group_id=1, beam="A", relation="co_frequency"):
    return {
        "classification": "frequency_match_candidate",
        "frequency_relation": {"relation": relation},
        "space": {
            "dataset_id": "space", "file": "data/ific3074.mdb", "dataset_kind": "space_ific_evaluation",
            "issue": 3074, "frequency_source_row": source_row, "notice_source_row": 1, "notice_id": 10,
            "administration": "X", "notice_type": "T", "provision": "P", "notice_publication_issue": 3074,
            "publication_date": "2026-06-23", "action_code": "A", "publication_part": "I", "status_code": "S",
            "group_id": group_id, "sequence_number": source_row, "beam_name": beam,
            "center_hz": (lower + upper) // 2, "bandwidth_hz": upper - lower,
            "frequency_min_hz": lower, "frequency_max_hz": upper, "satellites": [],
        },
        "finnish_usage": {
            "dataset_id": "finnish", "file": "data/stations.xlsx", "source_table": "Frequencies of interest",
            "source_row": 13, "station_number": "1", "frequency_role": "rx", "center_hz": 175,
            "bandwidth_hz": 150, "bandwidth_source": "channel_and_transmission_equal",
            "frequency_min_hz": 100, "frequency_max_hz": 250, "longitude": 24, "latitude": 60,
            "quality_flags": [],
        },
    }


class IntervalTests(unittest.TestCase):
    def test_overlapping_intervals_merge_but_gaps_remain(self):
        self.assertEqual(merge_closed_intervals([(1, 5), (4, 8), (10, 12)]), [
            {"frequency_min_hz": 1, "frequency_max_hz": 8},
            {"frequency_min_hz": 10, "frequency_max_hz": 12},
        ])


class ConsolidationTests(unittest.TestCase):
    def test_repeated_source_rows_become_one_traceable_case(self):
        cases = consolidate([candidate(1, 50, 150), candidate(2, 140, 300, group_id=2, beam="B")])
        self.assertEqual(len(cases), 1)
        case = cases[0]
        self.assertEqual(case["matched_frequency_segments_hz"], [{"frequency_min_hz": 100, "frequency_max_hz": 250}])
        self.assertEqual(case["evidence"]["frequency_source_rows"], [1, 2])
        self.assertEqual(case["evidence"]["raw_match_count"], 2)
        self.assertEqual(len(case["space_frequency_bands"]), 2)
        self.assertEqual(case["frequency_relation"]["relation"], "co_frequency")
        self.assertEqual(case["frequency_relation"]["overlap_fraction_of_protected"], 1.0)

    def test_adjacent_only_case_keeps_nearest_gap(self):
        cases = consolidate([candidate(1, 260, 400, relation="adjacent"), candidate(2, 20, 90, relation="adjacent")])
        relation = cases[0]["frequency_relation"]
        self.assertEqual(relation["relation"], "adjacent")
        self.assertEqual(relation["nearest_adjacent_separation_hz"], 10)
        self.assertEqual(relation["adjacent_sides"], ["above", "below"])
        self.assertEqual(cases[0]["matched_frequency_segments_hz"], [])

    def test_mislabelled_adjacent_record_is_rejected(self):
        with self.assertRaises(ValueError):
            consolidate([candidate(1, 50, 150, relation="adjacent")])

    def test_notice_rollup_counts_cases_by_relation(self):
        cases = consolidate([candidate(1, 50, 150)])
        rollup, = notice_rollups(cases)
        self.assertEqual(rollup["counts"], {"co_frequency_cases": 1, "adjacent_cases": 0,
                                            "review_cases": 1, "distinct_stations": 1})


if __name__ == "__main__":
    unittest.main()
