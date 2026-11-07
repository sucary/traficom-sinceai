import math
import unittest

from app.analysis.p1546_model import erp_kw_from_radiated_power, field_strength_dbuv_m
from app.analysis.terrestrial_criteria import base_threshold_dbuv_m, threshold_dbuv_m
from app.analysis.terrestrial_pipeline import (
    _geometry_segments, classify_event, haversine_km, nearest_assessment_point, nearest_point_on_segment,
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

    def test_distance_calculation(self):
        self.assertAlmostEqual(haversine_km(60, 25, 60, 25), 0)
        self.assertGreater(haversine_km(60, 25, 61, 25), 110)


class BoundaryGeometryTests(unittest.TestCase):
    def test_nearest_point_lies_between_vertices(self):
        # A meridian segment 60N-62N at 25E; the point at 61N 26E is closest to its middle.
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
        # GeoJSON edges are straight in lon/lat, so dense sampling of that line is the reference.
        self.assertAlmostEqual(distance, sampled, delta=0.01)

    def test_real_boundary_never_farther_than_nearest_vertex(self):
        segments, source = _geometry_segments()
        self.assertGreater(source["segment_count"], source["ring_count"])
        vertices = {pt for segment in segments for pt in segment}
        for latitude, longitude in ((60.0, 30.5), (69.5, 29.0), (65.5, 22.8), (59.4, 24.7), (68.3, 23.0)):
            _, distance = nearest_assessment_point(latitude, longitude, segments)
            vertex = min(haversine_km(latitude, longitude, *pt) for pt in vertices)
            self.assertLessEqual(distance, vertex + 1e-9)
            # Exhaustive reference: refine every segment without the projected pre-filter.
            exhaustive = min(nearest_point_on_segment(latitude, longitude, *segment)[1] for segment in segments)
            self.assertAlmostEqual(distance, exhaustive, places=6)


if __name__ == "__main__":
    unittest.main()
