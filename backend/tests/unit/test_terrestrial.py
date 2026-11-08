import math
import unittest

from app.analysis.p1546_model import erp_kw_from_radiated_power, field_strength_dbuv_m
from app.analysis.terrestrial_criteria import base_threshold_dbuv_m, threshold_dbuv_m
from app.analysis.terrestrial_pipeline import (
    _geometry_segments, _matching_protected_stations, classify_event, haversine_km,
    nearest_assessment_point, nearest_assessment_points_by_section, nearest_point_on_segment,
)


class TerrestrialCriteriaTests(unittest.TestCase):
    def test_a_1_2_3_frequency_bands_and_challenge_extension(self):
        cases = [(29.7, 0), (46.999, 0), (47, 6), (108, 12), (380, 18), (400, 20), (900, 20)]
        for frequency, expected in cases:
            with self.subTest(frequency=frequency):
                self.assertEqual(base_threshold_dbuv_m(frequency), expected)

    def test_bandwidth_correction_is_only_applied_when_explicit(self):
        self.assertEqual(threshold_dbuv_m(450, 50_000, False), (20, 0))
        threshold, correction = threshold_dbuv_m(450, 50_000, True)
        self.assertAlmostEqual(correction, 10 * math.log10(2))
        self.assertAlmostEqual(threshold, 20 + correction)


class TerrestrialEventTests(unittest.TestCase):
    def test_publication_and_amendment_classification(self):
        self.assertEqual(classify_event({"amend_type": "NOT AMENDED"}, {"1"}), "new")
        self.assertEqual(classify_event({"amend_type": "MAJOR"}, {"1"}), "modified")
        self.assertEqual(classify_event({"amend_type": "WITHDRAWAL"}, {"1"}), "withdrawn")
        self.assertEqual(classify_event({"amend_type": "NOT AMENDED"}, {"3"}), "withdrawn")
        self.assertEqual(classify_event({"amend_type": "NOT AMENDED"}, {"2"}), "recorded")
        self.assertEqual(classify_event({"amend_type": "NOT AMENDED", "mod_type": "NOT MODIFY"}, set()),
                         "not_published_in_issue")

    def test_every_matching_station_is_returned_and_duplicate_rows_are_grouped(self):
        stations = [
            {"station_number": "A", "latitude": 60.0, "longitude": 25.0,
             "frequency_min_hz": 99, "frequency_max_hz": 101, "source_row": 2, "dataset_id": "d"},
            {"station_number": "A", "latitude": 60.0, "longitude": 25.0,
             "frequency_min_hz": 98, "frequency_max_hz": 102, "source_row": 3, "dataset_id": "d"},
            {"station_number": "B", "latitude": 61.0, "longitude": 26.0,
             "frequency_min_hz": 100, "frequency_max_hz": 100, "source_row": 4, "dataset_id": "d"},
            {"station_number": "C", "latitude": 62.0, "longitude": 27.0,
             "frequency_min_hz": 200, "frequency_max_hz": 201, "source_row": 5, "dataset_id": "d"},
        ]
        matches = _matching_protected_stations(stations, 100)
        self.assertEqual([item["station_number"] for item in matches], ["A", "B"])
        self.assertEqual(matches[0]["station_source_rows"], [2, 3])
        self.assertEqual(len(matches[0]["matching_frequency_ranges_hz"]), 2)


class P1546AdapterTests(unittest.TestCase):
    def test_eirp_is_converted_to_erp(self):
        erp_kw, delta = erp_kw_from_radiated_power(30, "I")
        self.assertEqual(delta, -2.15)
        self.assertAlmostEqual(erp_kw, 10 ** (27.85 / 10) / 1000)

    def test_reference_implementation_smoke_value(self):
        field, loss = field_strength_dbuv_m(
            frequency_mhz=100,
            distance_km=100,
            effective_tx_height_m=75,
            erp_kw=1,
        )
        self.assertAlmostEqual(field, 27.1424, places=4)
        self.assertAlmostEqual(loss, 152.1576, places=4)

    def test_cold_sea_path_uses_distinct_propagation_curve(self):
        inputs = dict(frequency_mhz=600, distance_km=100, effective_tx_height_m=75, erp_kw=1)
        land, _ = field_strength_dbuv_m(**inputs, path_zone="Land")
        cold, _ = field_strength_dbuv_m(**inputs, path_zone="Cold")
        self.assertGreater(cold, land)

    def test_distance_calculation(self):
        self.assertAlmostEqual(haversine_km(60, 25, 60, 25), 0)
        self.assertGreater(haversine_km(60, 25, 61, 25), 110)


class BoundaryGeometryTests(unittest.TestCase):
    def test_nearest_point_lies_between_vertices(self):
        point, distance = nearest_point_on_segment(61.0, 26.0, (60.0, 25.0), (62.0, 25.0))
        self.assertAlmostEqual(point[1], 25.0, places=6)
        self.assertAlmostEqual(point[0], 61.0, delta=0.02)
        self.assertGreater(point[0], 60.0)
        self.assertLess(point[0], 62.0)
        self.assertAlmostEqual(distance, haversine_km(61.0, 26.0, *point), places=6)
        vertex = min(haversine_km(61.0, 26.0, 60.0, 25.0), haversine_km(61.0, 26.0, 62.0, 25.0))
        self.assertLess(distance, 55.0)
        self.assertGreater(vertex, 110.0)

    def test_projection_outside_the_arc_uses_the_endpoint(self):
        point, distance = nearest_point_on_segment(63.0, 25.5, (60.0, 25.0), (62.0, 25.0))
        self.assertAlmostEqual(point[0], 62.0, places=6)
        self.assertAlmostEqual(point[1], 25.0, places=6)
        self.assertAlmostEqual(distance, haversine_km(63.0, 25.5, 62.0, 25.0))

    def test_matches_dense_sampling_of_a_long_segment(self):
        start, end = (59.8, 22.0), (60.6, 27.9)
        _, distance = nearest_point_on_segment(61.3, 24.1, start, end)
        samples = [(start[0] + (end[0] - start[0]) * t / 20000, start[1] + (end[1] - start[1]) * t / 20000)
                   for t in range(20001)]
        sampled = min(haversine_km(61.3, 24.1, *pt) for pt in samples)
        self.assertAlmostEqual(distance, sampled, delta=0.01)

    def test_real_boundary_never_farther_than_nearest_vertex(self):
        segments, source = _geometry_segments()
        self.assertGreater(source["segment_count"], source["line_count"])
        self.assertEqual(set(source["segment_counts"]), {"land_border", "territorial_sea_outer_limit"})
        self.assertIn("outer limit", source["coverage"])
        vertices = {pt for segment in segments for pt in segment[:2]}
        for latitude, longitude in ((60.0, 30.5), (69.5, 29.0), (65.5, 22.8), (59.4, 24.7), (68.3, 23.0)):
            _, distance = nearest_assessment_point(latitude, longitude, segments)
            vertex = min(haversine_km(latitude, longitude, *pt) for pt in vertices)
            self.assertLessEqual(distance, vertex + 1e-9)

    def test_boundary_features_select_land_and_cold_sea_zones(self):
        segments, _ = _geometry_segments()
        _, _, land = nearest_assessment_point(61.85, 30.30, segments, include_metadata=True)
        _, _, sea = nearest_assessment_point(59.50, 24.00, segments, include_metadata=True)
        self.assertEqual((land["kind"], land["path_zone"]), ("land_border", "Land"))
        self.assertEqual((sea["kind"], sea["path_zone"]), ("territorial_sea_outer_limit", "Cold"))

    def test_every_official_boundary_section_gets_an_assessment_point(self):
        segments, source = _geometry_segments()
        points = nearest_assessment_points_by_section(61.85, 30.30, segments)
        self.assertEqual(len(points), source["line_count"])
        self.assertEqual(len({point["section_id"] for point in points}), source["line_count"])
        self.assertEqual({point["path_zone"] for point in points}, {"Land", "Cold"})


if __name__ == "__main__":
    unittest.main()


class AnomalyTests(unittest.TestCase):
    @staticmethod
    def result(i, adm, distance, event="new", result="below_threshold", margin=-5.0, erp_kw=0.02, height=20.0, freq=150.0):
        return {"assignment_id": str(i), "administration": adm, "event": event, "result": result,
                "margin_db": margin, "frequency_mhz": freq, "erp_kw": erp_kw, "effective_tx_height_m": height,
                "source_notice": {"bdwdth": 12.5},
                "assessments": [{"kind": "land_border", "distance_km": distance}]}

    def test_only_neighbours_are_observed(self):
        from app.analysis.terrestrial_pipeline import _anomalies
        results = [self.result(1, "RUS", 30.0, result="exceeds_threshold", margin=9.0),
                   self.result(2, "RUS", 400.0),
                   self.result(3, "SVN", 1800.0, result="outside_model_distance", margin=None)]
        flags = _anomalies([], [], {}, {}, results)
        self.assertEqual({f["administration"] for f in flags}, {"RUS"})
        summary = next(f for f in flags if f["type"] == "filing_summary")
        self.assertEqual(summary["evidence"]["within_range"], 2)
        self.assertEqual([e["assignment_id"] for e in summary["evidence"]["exceeding"]], ["1"])
        near = next(f for f in flags if f["type"] == "new_activity_near_border")
        self.assertEqual([a["assignment_id"] for a in near["evidence"]["assignments"]], ["1"])

    def test_outliers_need_a_meaningful_difference(self):
        from app.analysis.terrestrial_pipeline import _anomalies
        results = [self.result(i, "SVN", 1500.0, erp_kw=0.02) for i in range(9)]
        results += [self.result(9, "RUS", 200.0, erp_kw=0.04), self.result(10, "RUS", 200.0, erp_kw=2.0)]
        flags = [f for f in _anomalies([], [], {}, {}, results) if f["type"] == "parameter_outlier"]
        self.assertEqual([f["evidence"]["assignment_id"] for f in flags], ["10"])

    def test_new_station_class_for_neighbours(self):
        from app.analysis.terrestrial_pipeline import _anomalies
        row = lambda key, adm, cls: {"raw": {"terrakey": key, "adm": adm, "freq_assgn": 150.0, "stn_cls": cls}}
        previous = [row(i, "RUS", "FB") for i in range(5)]
        current = [row(10 + i, "RUS", "ML") for i in range(4)]
        parts = lambda rows: {r["raw"]["terrakey"]: {"1"} for r in rows}
        flags = _anomalies(previous, current, parts(previous), parts(current), [self.result(1, "RUS", 100.0)])
        self.assertIn(("new_station_class", "RUS ML"), {(f["type"], f["subject"]) for f in flags})

    def test_national_context_reports_finnish_mobile_use(self):
        from app.analysis.terrestrial_pipeline import national_context
        context = national_context(152.025)
        self.assertIn(context["mobile_in_finland"], {"primary", "secondary", "not_listed"})
        self.assertTrue(context["m4_bands"])
