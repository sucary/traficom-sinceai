import math
import unittest

from app.analysis.pfd_calculation import (
    EARTH_RADIUS_KM, calculate_case, margin_class, constellation_parameters, gso_geometry, max_elevation_deg,
    power_in_reference_bandwidth, slant_range_km, spreading_db,
)
from app.reference.pfd_criteria import load_criteria


class GeometryTests(unittest.TestCase):
    def test_gso_overhead_on_equator(self):
        elevation, distance = gso_geometry(0, 10, 10)
        self.assertAlmostEqual(elevation, 90)
        self.assertAlmostEqual(distance, 42164.0 - EARTH_RADIUS_KM, places=3)

    def test_gso_from_latitude_60_same_longitude(self):
        elevation, _ = gso_geometry(60, 25, 25)
        expected = math.degrees(math.atan((0.5 - EARTH_RADIUS_KM / 42164.0) / math.sin(math.radians(60))))
        self.assertAlmostEqual(elevation, expected, places=6)
        self.assertAlmostEqual(elevation, 21.9, delta=0.1)

    def test_gso_below_horizon_from_finland(self):
        elevation, _ = gso_geometry(65, 25, 160)
        self.assertLess(elevation, 0)

    def test_slant_range_limits(self):
        self.assertAlmostEqual(slant_range_km(90, 550), 550, places=6)
        self.assertAlmostEqual(slant_range_km(0, 550), math.sqrt((EARTH_RADIUS_KM + 550) ** 2 - EARTH_RADIUS_KM ** 2))

    def test_max_elevation_limited_by_inclination(self):
        self.assertEqual(max_elevation_deg(60, 97, 550), 90)  # sun-synchronous reaches 83° latitude
        self.assertLess(max_elevation_deg(65, 53, 550), 30)   # 53° shell never overhead in Finland
        self.assertLess(max_elevation_deg(68, 30, 550), 0)    # not visible at all


class EmissionTests(unittest.TestCase):
    def test_density_converted_and_capped_by_total_power(self):
        emission = {"maximum_power_density_dbw_per_hz": -50.0, "peak_envelope_power_dbw": 5.0}
        self.assertEqual(power_in_reference_bandwidth(emission, 4000), (-50 + 10 * math.log10(4000), False))
        self.assertEqual(power_in_reference_bandwidth(emission, 1_000_000), (5.0, True))


class ConstellationTests(unittest.TestCase):
    def test_x_and_y_from_filed_counts(self):
        profile = {"orbit_records": [{"nbr_sat_pl": 100}, {"nbr_sat_pl": 69}],
                   "non_geo_records": [{"nbr_sat_nh": 10, "nbr_sat_sh": 4}]}
        result = constellation_parameters(profile)
        self.assertEqual(result["satellites_in_constellation"], 169)
        self.assertAlmostEqual(result["values"]["X"], 5 / 119 * 119)
        self.assertAlmostEqual(result["values"]["Y"], 5)

    def test_large_constellation_needs_nv(self):
        result = constellation_parameters({"orbit_records": [{"nbr_sat_pl": 1500}], "non_geo_records": []})
        self.assertNotIn("X", result["values"])


def readiness(lat=60.0, lon=25.0, segments=((3_700_000_000, 3_702_000_000),)):
    return {
        "case_id": "c", "readiness": "ready_with_worst_case_assumptions", "frequency_profile_ids": ["p"],
        "notice_profile_id": "n", "frequency_relation": {"relation": "co_frequency"},
        "matched_frequency_segments_hz": [{"frequency_min_hz": a, "frequency_max_hz": b} for a, b in segments],
        "finnish_station": {"station_number": "1", "source_row": 1, "latitude": lat, "longitude": lon},
    }


def profile(density=-47.4, peak=13.1, gain=22.6, band=(3690.0, 3710.0)):
    return {"frequency_profile_id": "p", "frequency": {"minimum_mhz_source": band[0], "maximum_mhz_source": band[1]},
            "satellite_beams": [{"maximum_isotropic_gain_db": gain, "source_row": 1}],
            "emissions": [{"maximum_power_density_dbw_per_hz": density, "peak_envelope_power_dbw": peak, "source_row": 1}]}


BAND = {"frequency_min_hz": 3_700_000_000, "frequency_max_hz": 3_702_000_000, "bandwidth_hz": 2_000_000}


class CaseTests(unittest.TestCase):
    document = load_criteria()

    def test_gso_case_hand_calculation(self):
        notice = {"notice_id": 1, "notice_object": "geostationary_satellite_network", "geo_records": [{"long_nom": 25.0}]}
        result = calculate_case(readiness(), notice, [profile()], BAND, 3.0, self.document)
        elevation, distance = gso_geometry(60, 25, 25)
        pfd = -47.4 + 10 * math.log10(4000) + 22.6 - spreading_db(distance)
        limit = -152 + 0.5 * (elevation - 5)
        self.assertEqual(result["result"]["governing_criterion_id"], "T21-4-3400-4200-FSS-GSO")
        self.assertAlmostEqual(result["result"]["pfd_db"], pfd, places=1)
        self.assertAlmostEqual(result["result"]["worst_margin_db"], limit - pfd, places=1)
        citation = result["result"]["regulation_citation"]
        self.assertEqual(citation["edition"], "2024")
        self.assertEqual(citation["provision"], "RR Article 21, No. 21.16, Table 21-4")
        self.assertEqual(citation["pdf_page"], 297)
        self.assertEqual(len(citation["source_sha256"]), 64)

    def test_invisible_gso_is_not_a_concern(self):
        notice = {"notice_id": 1, "notice_object": "geostationary_satellite_network", "geo_records": [{"long_nom": 160.0}]}
        result = calculate_case(readiness(lat=65), notice, [profile()], BAND, 3.0, self.document)
        self.assertEqual(result["result"]["status"], "not_visible")

    def test_non_gso_sweep_finds_worst_angle_not_just_overhead(self, altitude=8000):
        notice = {"notice_id": 2, "notice_object": "non_geostationary_satellite_network", "geo_records": [],
                  "non_geo_records": [{"nbr_sat_nh": 1, "nbr_sat_sh": 1}],
                  "orbit_records": [{"source_row": 1, "nbr_sat_pl": 1, "perig_km": altitude, "apog_km": altitude, "inclin_ang": 97}]}
        result = calculate_case(readiness(), notice, [profile()], BAND, 3.0, self.document)
        evaluation = next(e for e in result["evaluations"] if e["criterion_id"] == "T21-4-3400-4200-FSS-NGSO")
        self.assertEqual(evaluation["status"], "computed")
        # Brute-force check of the reported minimum margin.
        eirp = min(-47.4 + 60, 13.1) + 22.6
        margins = [(-138 if a <= 5 else -138 + 12 * (a - 5) / 20 if a <= 25 else -126)
                   - (eirp - spreading_db(slant_range_km(a, altitude))) for a in [i / 10 for i in range(901)]]
        self.assertAlmostEqual(evaluation["margin_db"], min(margins), places=1)
        # At medium-orbit altitude the stricter low-angle limit dominates over the shorter overhead distance.
        self.assertLessEqual(evaluation["worst_elevation_deg"], 5)
        self.assertGreater(evaluation["max_pfd_db"], evaluation["pfd_db"])

    def test_earth_station_notice_skipped(self):
        notice = {"notice_id": 3, "notice_object": "specific_earth_station"}
        result = calculate_case(readiness(), notice, [profile()], BAND, 3.0, self.document)
        self.assertEqual(result["result"]["status"], "not_space_station")



NGSO_NOTICE = {"notice_id": 9, "notice_object": "non_geostationary_satellite_network", "geo_records": [],
               "non_geo_records": [{"nbr_sat_nh": 1, "nbr_sat_sh": 1}],
               "orbit_records": [{"source_row": 1, "nbr_sat_pl": 1, "perig_km": 500, "apog_km": 500, "inclin_ang": 97}]}
GSO_NOTICE = {"notice_id": 1, "notice_object": "geostationary_satellite_network", "geo_records": [{"long_nom": 25.0}]}


def profile_at(pid, low_mhz, high_mhz, density):
    item = profile(density=density, peak=None, band=(low_mhz, high_mhz))
    item["frequency_profile_id"] = pid
    return item


class ReviewFeedbackTests(unittest.TestCase):
    document = load_criteria()

    def test_margin_class_uses_full_precision(self):
        self.assertEqual(margin_class(-0.004, 3.0), "exceeds_limit")
        self.assertEqual(margin_class(2.996, 3.0), "near_limit")
        self.assertEqual(margin_class(3.0, 3.0), "below_limit")

    def test_unconfirmed_applicability_gives_candidate_verdicts(self):
        result = calculate_case(readiness(), GSO_NOTICE, [profile()], BAND, 3.0, self.document)["result"]
        self.assertTrue(result["status"].startswith("candidate_"))
        self.assertFalse(result["applicability_confirmed"])
        self.assertIn(result["margin_class"], {"exceeds_limit", "near_limit", "below_limit"})

    def test_multi_segment_result_independent_of_segment_order(self):
        segments = ((3_700_000_000, 3_702_000_000), (3_800_000_000, 3_802_000_000))
        profiles = [profile_at("p", 3690.0, 3710.0, -90.0), profile_at("q", 3790.0, 3810.0, -40.0)]
        margins = []
        for order in (segments, segments[::-1]):
            case = readiness(segments=order)
            case["frequency_profile_ids"] = ["p", "q"]
            margins.append(calculate_case(case, GSO_NOTICE, profiles, BAND, 3.0, self.document)["result"]["worst_margin_db"])
        self.assertEqual(margins[0], margins[1])
        loud_only = readiness(segments=segments[1:])
        expected = calculate_case(loud_only, GSO_NOTICE, profiles[1:], BAND, 3.0, self.document)["result"]["worst_margin_db"]
        self.assertEqual(margins[0], expected)

    def test_sar_exceedance_needs_special_method_but_generic_pass_holds(self):
        sar = readiness(segments=((10_000_000_000, 10_002_000_000),))
        loud = calculate_case(sar, NGSO_NOTICE, [profile_at("p", 9990.0, 10010.0, -20.0)], BAND, 3.0, self.document)
        self.assertEqual(loud["result"]["status"], "special_method_required")
        evaluation = loud["evaluations"][0]
        self.assertIn("screening_estimate", evaluation)
        self.assertNotIn("margin_db", evaluation)
        quiet = calculate_case(sar, NGSO_NOTICE, [profile_at("p", 9990.0, 10010.0, -150.0)], BAND, 3.0, self.document)
        self.assertEqual(quiet["result"]["status"], "candidate_below_limit")

    def test_resolution_679_row_never_uses_generic_verdict(self):
        isl = readiness(segments=((28_000_000_000, 28_002_000_000),))
        quiet = calculate_case(isl, NGSO_NOTICE, [profile_at("p", 27990.0, 28010.0, -150.0)], BAND, 3.0, self.document)
        self.assertEqual(quiet["result"]["status"], "special_method_required")



def classed(station_classes, **kwargs):
    item = profile(**kwargs)
    item["station_classes"] = station_classes
    return item


class ServiceApplicabilityTests(unittest.TestCase):
    document = load_criteria()

    def test_matching_station_class_confirms_verdict(self):
        result = calculate_case(readiness(), GSO_NOTICE, [classed(["EC"])], BAND, 3.0, self.document)["result"]
        self.assertTrue(result["applicability_confirmed"])
        self.assertEqual(result["status"], result["margin_class"])

    def test_known_service_mismatch_makes_row_not_applicable(self):
        result = calculate_case(readiness(), GSO_NOTICE, [classed(["EN"])], BAND, 3.0, self.document)["result"]
        self.assertEqual(result["status"], "no_criterion")

    def test_telemetry_class_is_ambiguous_not_a_mismatch(self):
        result = calculate_case(readiness(), GSO_NOTICE, [classed(["ER"])], BAND, 3.0, self.document)["result"]
        self.assertTrue(result["status"].startswith("candidate_"))

    def test_only_matching_groups_decide_the_verdict(self):
        loud_other = classed(["EN"], density=-20.0)
        quiet_fss = classed(["EC"], density=-90.0)
        loud_other["frequency_profile_id"], quiet_fss["frequency_profile_id"] = "a", "b"
        case = readiness()
        case["frequency_profile_ids"] = ["a", "b"]
        result = calculate_case(case, GSO_NOTICE, [loud_other, quiet_fss], BAND, 3.0, self.document)["result"]
        self.assertEqual(result["status"], "below_limit")

    def test_post_1995_non_gso_fss_fails_footnote_21_16_6a(self):
        notice = dict(NGSO_NOTICE, notice_received_date="2024-01-01 00:00:00")
        case = readiness(segments=((18_000_000_000, 18_002_000_000),))
        result = calculate_case(case, notice, [classed(["EC"], band=(17990.0, 18010.0))], BAND, 3.0, self.document)
        rows = {e["criterion_id"]: e["applicability"] for e in result["evaluations"]}
        self.assertEqual(rows["T21-4-17.7-19.3-FSS-GSO-ISS-METSAT"], "not_applicable")
        self.assertEqual(rows["T21-4-17.7-19.3-FSS-NGSO-X"], "applicable")



class ParameterBoundTests(unittest.TestCase):
    document = load_criteria()

    def test_limits_never_increase_with_x_or_y(self):
        from app.reference.pfd_criteria import evaluate_formula
        for criterion in self.document["criteria"]:
            for name in criterion["parameters"]:
                for segment in criterion["segments"]:
                    for angle in (segment["elev_min_deg"], (segment["elev_min_deg"] + segment["elev_max_deg"]) / 2,
                                  segment["elev_max_deg"]):
                        low = evaluate_formula(segment["formula"], angle, X=1.0, Y=1.0)
                        high = evaluate_formula(segment["formula"], angle, **{"X": 1.0, "Y": 1.0, name: 40.0})
                        self.assertLessEqual(high, low + 1e-9, criterion["criterion_id"])

    def test_large_constellation_exceedance_decided_by_lower_bound(self):
        notice = dict(NGSO_NOTICE, notice_received_date="2024-01-01 00:00:00",
                      orbit_records=[{"source_row": 1, "nbr_sat_pl": 1500, "perig_km": 500, "apog_km": 500, "inclin_ang": 97}])
        case = readiness(segments=((18_000_000_000, 18_002_000_000),))
        loud = calculate_case(case, notice, [classed(["EC"], density=-20.0, peak=None, band=(17990.0, 18010.0))],
                              BAND, 3.0, self.document)
        self.assertEqual(loud["result"]["status"], "exceeds_limit")
        quiet = calculate_case(case, notice, [classed(["EC"], density=-150.0, peak=None, band=(17990.0, 18010.0))],
                               BAND, 3.0, self.document)
        self.assertEqual(quiet["result"]["status"], "parameter_missing")



class SharingConditionTests(unittest.TestCase):
    document = load_criteria()

    def test_sar_below_10_ghz_has_no_applicable_limit_in_finland(self):
        # 9.9-10 GHz Region 1: fixed is secondary (5.477 does not list Finland) -> No. 21.16 not met.
        sar = readiness(segments=((9_950_000_000, 9_952_000_000),))
        result = calculate_case(sar, NGSO_NOTICE, [classed(["E3"], density=-20.0, peak=None, band=(9940.0, 9960.0))],
                                BAND, 3.0, self.document)
        evaluation = result["evaluations"][0]
        self.assertEqual(evaluation["applicability"], "not_applicable")
        self.assertEqual(evaluation["not_applicable_reason"], "rr_21_16_equal_rights_sharing_not_met")
        self.assertEqual(result["result"]["status"], "no_criterion")

    def test_unallocated_satellite_service_gets_rr_4_4_status(self):
        # Mobile-satellite has no Region 1 allocation in 2 500-2 690 MHz.
        mss = readiness(segments=((2_600_000_000, 2_602_000_000),))
        result = calculate_case(mss, GSO_NOTICE, [classed(["EI"], band=(2590.0, 2610.0))], BAND, 3.0, self.document)
        self.assertEqual(result["result"]["status"], "unallocated_service_rr_4_4")
        self.assertIn("reference_pfd", result["result"])

    def test_sharing_and_m4_context_reported(self):
        result = calculate_case(readiness(), GSO_NOTICE, [classed(["EC"])], BAND, 3.0, self.document)
        evaluation = result["evaluations"][0]
        self.assertEqual([r["result"] for r in evaluation["sharing"]["article5_region1"]], ["equal_rights"])
        self.assertIn(result["result"]["national_context_m4"], {"primary", "secondary", "not_listed"})


if __name__ == "__main__":
    unittest.main()
