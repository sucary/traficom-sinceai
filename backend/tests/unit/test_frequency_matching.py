import unittest

from app.analysis.frequency_matching import frequency_relation, match_intervals, protected_bands, satellite_band


class ProtectedBandTests(unittest.TestCase):
    def test_rx_and_tx_are_both_protected_and_equal_values_are_deduplicated(self):
        station = {"rx_frequency_hz": 1000, "tx_frequency_hz": 2000, "effective_bandwidth_hz": 100}
        self.assertEqual([band["frequency_role"] for band in protected_bands(station)], ["rx", "tx"])
        station["tx_frequency_hz"] = 1000
        self.assertEqual(protected_bands(station)[0]["frequency_role"], "rx_tx")

    def test_missing_rx_falls_back_to_tx(self):
        station = {"rx_frequency_hz": None, "tx_frequency_hz": 2000, "effective_bandwidth_hz": 100}
        self.assertEqual(protected_bands(station)[0]["frequency_role"], "tx")


class SatelliteBandTests(unittest.TestCase):
    def test_mhz_and_khz_source_units_are_normalized(self):
        band = satellite_band({"freq_mhz": 100.0, "freq_min": 99.5, "freq_max": 100.5, "bdwdth": 1000})
        self.assertEqual(band, {"center_hz": 100000000, "bandwidth_hz": 1000000,
                                "frequency_min_hz": 99500000, "frequency_max_hz": 100500000})

    def test_closed_interval_edges_match(self):
        satellite = [{"frequency_min_hz": 100, "frequency_max_hz": 200}]
        protected = [{"frequency_min_hz": 200, "frequency_max_hz": 250},
                     {"frequency_min_hz": 201, "frequency_max_hz": 250}]
        self.assertEqual(len(list(match_intervals(satellite, protected))), 1)


class AdjacencyTests(unittest.TestCase):
    protected = [{"frequency_min_hz": 1000, "frequency_max_hz": 1100, "bandwidth_hz": 100}]

    def test_adjacent_within_one_bandwidth_is_flagged_only_when_enabled(self):
        satellite = [{"frequency_min_hz": 1150, "frequency_max_hz": 1300}]
        self.assertEqual(list(match_intervals(satellite, self.protected, 0)), [])
        (_, _, relation), = match_intervals(satellite, self.protected, 1)
        self.assertEqual(relation["relation"], "adjacent")
        self.assertEqual(relation["separation_hz"], 50)
        self.assertEqual(relation["satellite_side"], "above")
        self.assertEqual(relation["adjacent_guard_hz"], 100)

    def test_beyond_guard_is_not_flagged(self):
        satellite = [{"frequency_min_hz": 700, "frequency_max_hz": 899}]
        self.assertEqual(list(match_intervals(satellite, self.protected, 1)), [])

    def test_co_frequency_overlap_metrics(self):
        relation = frequency_relation({"frequency_min_hz": 1050, "frequency_max_hz": 2000}, self.protected[0])
        self.assertEqual((relation["relation"], relation["overlap_hz"], relation["satellite_side"]),
                         ("co_frequency", 50, "partial"))
        self.assertEqual(relation["overlap_fraction_of_protected"], 0.5)
        covering = frequency_relation({"frequency_min_hz": 0, "frequency_max_hz": 5000}, self.protected[0])
        self.assertEqual(covering["satellite_side"], "covers")


if __name__ == "__main__":
    unittest.main()
