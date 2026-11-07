import unittest

from app.analysis.calculation_readiness import assess_case, build_frequency_profile, build_notice_profile


class ProfileTests(unittest.TestCase):
    def test_exact_carrier_link_builds_ready_frequency_profile(self):
        frequency = {"source_row": 7, "raw": {"ntc_id": 1, "grp_id": 2, "seq_no": 3, "emi_rcp": "E", "beam_name": "A"}}
        groups = {2: {"source_row": 8, "raw": {"grp_id": 2}}}
        emissions = {2: [{"source_row": 9, "raw": {"seq_no": 4, "pep_max": 10, "pwr_ds_max": -20}}]}
        beams = {(1, "E", "A"): [{"source_row": 10, "raw": {"gain": 20}}]}
        profile = build_frequency_profile("d", frequency, groups, emissions, {(2, 3): [4]}, beams)
        self.assertTrue(profile["profile_ready"])
        self.assertEqual(profile["emission_linkage"], "exact_via_carrier_fr")

    def test_group_fallback_is_explicit_worst_case_assumption(self):
        frequency = {"source_row": 7, "raw": {"ntc_id": 1, "grp_id": 2, "seq_no": 3, "emi_rcp": "E", "beam_name": "A"}}
        groups = {2: {"source_row": 8, "raw": {}}}
        emissions = {2: [{"source_row": 9, "raw": {"seq_no": 4, "pep_max": 10}}]}
        beams = {(1, "E", "A"): [{"source_row": 10, "raw": {"gain": 20}}]}
        profile = build_frequency_profile("d", frequency, groups, emissions, {}, beams)
        self.assertTrue(profile["profile_ready"])
        self.assertIn("consider_all_group_emissions_when_carrier_link_is_absent", profile["assumptions"])

    def test_non_gso_notice_requires_orbit_altitude(self):
        profile = build_notice_profile("d", 1, "non_geostationary_satellite_network", [],
                                       [{"source_row": 1, "raw": {"ntc_id": 1}}], [])
        self.assertFalse(profile["orbit_context_ready"])
        self.assertIn("non_gso_orbit_altitude", profile["missing_inputs"])


class CaseReadinessTests(unittest.TestCase):
    def test_ready_case_records_no_calculation(self):
        case = {"case_id": "c", "regulatory_classification": {"disposition": "eligible_for_later_calculation"}}
        station = {"dataset_id": "f", "source_row": 1, "station_number": "1", "longitude": 24, "latitude": 60}
        notice = {"notice_profile_id": "n", "missing_inputs": [], "orbit_context_ready": True}
        profile = {"frequency_profile_id": "p", "profile_ready": True, "missing_inputs": [], "assumptions": []}
        result = assess_case(case, station, notice, [profile])
        self.assertEqual(result["readiness"], "ready_with_worst_case_assumptions")
        self.assertFalse(result["technical_calculations_performed"])


if __name__ == "__main__":
    unittest.main()
