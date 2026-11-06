import unittest

from app.ingestion.specs import HEADERS
from app.ingestion.stations import frequency_hz, normalize_station


class FrequencyTests(unittest.TestCase):
    def test_unit_conversion(self):
        self.assertEqual(frequency_hz("87.900 MHz"), 87900000)
        self.assertEqual(frequency_hz("300.000 kHz"), 300000)
        self.assertEqual(frequency_hz("1.25 GHz"), 1250000000)

    def test_missing_and_invalid_units(self):
        self.assertIsNone(frequency_hz(None))
        for value in ("100", "1 bananas", "0 MHz", "-1 MHz", "0.5 Hz"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                frequency_hz(value)


class StationTests(unittest.TestCase):
    def raw(self, **changes):
        row = dict.fromkeys(HEADERS)
        row.update(station_number=123, longitude=24, latitude=60, rx_frequency="100 MHz",
                   tx_frequency="100 MHz", channel_bandwidth="25 kHz", reported_power=5,
                   power_unit="kW", ground_height_m=20, antenna_height_agl_m=10,
                   antenna_height_asl_m=30)
        row.update(changes)
        return row

    def test_units_and_provenance(self):
        row = normalize_station(self.raw(), 13, "dataset")
        self.assertEqual(row["reported_power_w"], 5000)
        self.assertEqual(row["rx_frequency_hz"], 100000000)
        self.assertEqual(row["source_row"], 13)
        self.assertEqual(row["quality_flags"], [])

    def test_invalid_values_preserved(self):
        raw = self.raw(antenna_height_agl_m=-2, antenna_height_asl_m=18, latitude=95)
        row = normalize_station(raw, 14, "dataset")
        self.assertIn("antenna_below_1m_agl", row["quality_flags"])
        self.assertIn("antenna_asl_below_ground", row["quality_flags"])
        self.assertIn("invalid_coordinates", row["quality_flags"])
        self.assertEqual(row["antenna_height_agl_m"], -2)
        self.assertEqual(row["raw"], raw)

    def test_missing_power_not_zero(self):
        row = normalize_station(self.raw(reported_power=None), 13, "dataset")
        self.assertIsNone(row["reported_power_w"])

    def test_bad_frequency_is_flagged(self):
        row = normalize_station(self.raw(rx_frequency="100"), 13, "dataset")
        self.assertIsNone(row["rx_frequency_hz"])
        self.assertIn("invalid_rx_frequency", row["quality_flags"])


if __name__ == "__main__":
    unittest.main()
