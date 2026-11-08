import unittest

from app.reference.allocations import (
    article5_assessment, load_article5, load_m4, m4_assessment, m4_service_tokens,
)
from app.reference.pfd_criteria import criterion_by_id, load_criteria
from app.reference.services import criterion_tokens

M, G = 1_000_000, 1_000_000_000


def results(criterion_id, tokens, lower, upper):
    return [r["result"] for r in article5_assessment(criterion_by_id(criterion_id), set(tokens), lower, upper)]


class Article5StructureTests(unittest.TestCase):
    def test_bands_sorted_and_non_overlapping(self):
        bands = load_article5()["bands"]
        for left, right in zip(bands, bands[1:]):
            self.assertLessEqual(left["frequency_max_hz"], right["frequency_min_hz"], right["label"])
            self.assertLess(left["frequency_min_hz"], left["frequency_max_hz"])

    def test_every_finland_table_21_4_band_is_covered(self):
        for criterion in load_criteria()["criteria"]:
            for band in criterion["bands"]:
                if not band["applies_in_finland"]:
                    continue
                found = results(criterion["criterion_id"], criterion_tokens(criterion),
                                band["frequency_min_hz"], band["frequency_max_hz"])
                self.assertNotIn("no_article5_entry", found, f'{criterion["criterion_id"]} {band["label"]}')


class EqualRightsTests(unittest.TestCase):
    def test_shared_with_primary_fixed(self):
        self.assertEqual(results("T21-4-1525-2300-METSAT-SR-SO-EESS", {"SR"}, 2210 * M, 2220 * M), ["equal_rights"])
        self.assertEqual(results("T21-4-3400-4200-FSS-GSO", {"FSS"}, 3900 * M, 3910 * M), ["equal_rights"])

    def test_secondary_space_service_against_primary_fixed_is_unequal(self):
        self.assertEqual(results("T21-4-1525-2300-METSAT-SR-SO-EESS", {"EESS"}, 1526 * M, 1527 * M), ["unequal_rights"])
        self.assertEqual(results("T21-4-1525-2300-METSAT-SR-SO-EESS", {"SO"}, 1526 * M, 1527 * M), ["equal_rights"])

    def test_sar_band_split_at_10_ghz(self):
        self.assertEqual(results("T21-4-9900-10400-EESS-ACTIVE", {"EESS_ACTIVE"}, 9950 * M, 10050 * M),
                         ["unequal_rights", "equal_rights"])

    def test_unallocated_space_service(self):
        self.assertEqual(results("T21-4-2500-2690-FSS-BSS-RDSS-MSS", {"FSS"}, 2505 * M, 2510 * M),
                         ["service_not_allocated"])
        self.assertEqual(results("T21-4-2500-2690-FSS-BSS-RDSS-MSS", {"BSS"}, 2600 * M, 2610 * M), ["equal_rights"])

    def test_footnote_allocation_counts(self):
        self.assertEqual(results("T21-4-11.7-12.75-FSS-NGSO-NONHEO", {"FSS"}, 12 * G, int(12.1 * G)), ["equal_rights"])

    def test_rows_with_stated_sharing_basis(self):
        self.assertEqual(results("T21-4-1670-1700-EESS-METSAT", {"METSAT"}, 1695 * M, 1696 * M), ["equal_rights"])
        self.assertEqual(results("T21-4-13.4-13.65-FSS-GSO", {"FSS"}, int(13.5 * G), int(13.6 * G)), ["equal_rights"])
        self.assertEqual(results("T21-4-31.0-31.3-34.7-35.2-SR", {"SR"}, int(31.1 * G), int(31.2 * G)),
                         ["explicitly_applicable"])

    def test_earth_to_space_only_allocation_does_not_count(self):
        self.assertEqual(results("T21-4-1525-2300-METSAT-SR-SO-EESS", {"SR"}, 2050 * M, 2060 * M), ["equal_rights"])
        self.assertEqual(results("T21-4-1525-2300-METSAT-SR-SO-EESS", {"METSAT"}, 1671 * M, 1672 * M), ["equal_rights"])
        allocations = article5_assessment(criterion_by_id("T21-4-2500-2690-FSS-BSS-RDSS-MSS"), {"MSS"}, 2505 * M, 2506 * M)
        self.assertEqual([r["result"] for r in allocations], ["service_not_allocated"])


class M4Tests(unittest.TestCase):
    def test_service_name_mapping(self):
        self.assertEqual(m4_service_tokens("FIXED"), ({"FIXED"}, "primary", []))
        self.assertEqual(m4_service_tokens("Fixed satellite (space-to-Earth)")[:2], ({"FSS"}, "secondary"))
        self.assertEqual(m4_service_tokens("MOBILE AND FIXED")[0], {"FIXED", "MOBILE"})
        self.assertEqual(m4_service_tokens("LAND MOBILE")[0], {"MOBILE"})
        self.assertEqual(m4_service_tokens("Mobile-Satellite (space-to-Earth)")[:2], ({"MSS"}, "secondary"))
        self.assertEqual(m4_service_tokens("SPACE OPERATION (SPACE-TO-EARTH) ")[0], {"SO"})

    def test_every_m4_service_is_mapped(self):
        unmapped = {name for band in load_m4() for name, s in band["services"].items()
                    if any(t.startswith("OTHER:") for t in s["tokens"])}
        known_other = {"(not allocated)", "AERONAUTICAL RADIONAVIGATION", "Aeronautical radionavigation", "AMATEUR",
                       "Amateur", "AMATEUR-SATELLITE", "Amateur-Satellite", "Amateur-Satellite (space-to-Earth)",
                       "MARITIME RADIONAVIGATION", "Maritime radionavigation", "RADIO ASTRONOMY", "Radio Astronomy",
                       "RADIOLOCATION", "Radiolocation", "RADIONAVIGATION", "RADIONAVIGATION-SATELLITE",
                       "RADIONAVIGATION-SATELLITE (EARTH-TO-SPACE)",
                       "RADIONAVIGATION-SATELLITE (SPACE-TO-EARTH, SPACE-TO-SPACE)",
                       "STANDARD FREQUENCY AND TIME SIGNAL", "STANDARD FREQUENCY AND TIME SIGNAL-SATELLITE"}
        self.assertLessEqual(unmapped, known_other)

    def test_finnish_national_partner(self):
        self.assertEqual(m4_assessment(["FIXED", "MOBILE"], {"SR"}, 2210 * M, 2220 * M)["partner_in_finland"], "primary")
        self.assertEqual(m4_assessment(["FIXED", "MOBILE"], {"FSS"}, int(11 * G), int(11.1 * G))["partner_in_finland"],
                         "not_listed")


if __name__ == "__main__":
    unittest.main()
