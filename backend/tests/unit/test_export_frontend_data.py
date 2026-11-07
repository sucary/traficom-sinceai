"""Regression tests: notice exports must keep caveats case-specific.

Modelled on two real IFIC 3074 errors. The CSN-SSO worst case (3.5 GHz fixed-satellite,
equal rights) was described with RR No. 4.4 non-allocation that only applied to its
2.5 GHz mobile-satellite cases. The RGS-N 4 kHz worst case was described with the
4 kHz-to-1 MHz scaling caveat that only applied to other cases.
"""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_frontend_data.py"
spec = importlib.util.spec_from_file_location("export_frontend_data", SCRIPT)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)

SCALING = ("density_scaled_from_worst_4khz: below 15 GHz the filed maximum power density is averaged "
           "over the worst 4 kHz; scaling it to the reference bandwidth can overstate pfd")


def case(case_id, notice_id, station, status, margin, criterion, caveats, rr44=False, bandwidth=1_000_000):
    if status == "unallocated_service_rr_4_4":
        result = {"status": status}
    else:
        result = {"status": status, "worst_margin_db": margin, "pfd_db": -100.0, "limit_db": -100.0 - margin,
                  "reference_bandwidth_hz": bandwidth, "worst_elevation_deg": 10.0,
                  "governing_criterion_id": criterion,
                  "regulation_citation": {"document": "RR", "provision": "Table 21-4", "printed_page": 287,
                                          "pdf_page": 297, "source_url": "https://example.test"}}
    if rr44:
        result["rr_4_4_unallocated_rows"] = [{"criterion_id": "other-row"}]
    return {
        "case_id": case_id, "notice_id": notice_id, "satellite_names": ["SAT"], "assumptions": ["Peak gain"],
        "space": {"administration": "CHN", "provision": "9.1/IA", "publication_date": "2026-06-23 00:00:00"},
        "finnish_station": {"station_number": station, "latitude": 60.0, "longitude": 25.0, "source_row": 10,
                            "protected_band": {"frequency_min_hz": 3.5e9, "frequency_max_hz": 3.6e9}},
        "evaluations": [{"criterion_id": criterion, "caveats": caveats},
                        {"criterion_id": "not-governing", "caveats": ["mean_pfd_limit: not this row"]}],
        "result": result,
        "evidence": {"source_datasets": {"space": {"file": "data/ific9999.mdb", "sha256": "a" * 64},
                                         "finnish_workbook": {"file": "data/wb.xlsx", "sha256": "b" * 64}},
                     "source_rows": {"notice": {"table": "notice", "source_row": 1}}},
    }


class CaseSpecificCaveatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        folder = Path(cls.temporary.name) / "ific9999"
        (folder / "pfd-calculations").mkdir(parents=True)
        records = [
            # CSN-SSO pattern: worst case has only the scaling caveat; other cases are RR 4.4.
            case("csn-worst", 1, "100", "exceeds_limit", -42.94, "FSS-NGSO", [SCALING]),
            case("csn-mss-1", 1, "101", "unallocated_service_rr_4_4", None, None, []),
            case("csn-mss-2", 1, "102", "unallocated_service_rr_4_4", None, None, []),
            # RGS-N pattern: 4 kHz worst case without caveats; another case carries the scaling caveat.
            case("rgs-worst", 2, "200", "exceeds_limit", -21.43, "FSS-4KHZ", [], bandwidth=4000),
            case("rgs-other", 2, "201", "near_limit", 1.0, "FSS-1MHZ", [SCALING]),
            # Worst case whose other rows are RR 4.4: flagged, but not as a headline caveat.
            case("mixed-worst", 3, "300", "exceeds_limit", -5.0, "FSS-NGSO", [], rr44=True),
        ]
        (folder / "pfd-calculations" / "case_pfd_results.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        (folder / "pfd-calculations" / "pfd_summary.json").write_text(json.dumps({
            "counts": {}, "criteria_transcription_status": "unverified_ai_transcription",
            "run": {"run_id": "r" * 64}}), encoding="utf-8")
        _, notices = export.space_issue(folder, {})
        cls.notices = {n["noticeId"]: n for n in notices}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_csn_sso_worst_case_does_not_claim_rr_4_4(self):
        notice = self.notices["1"]
        self.assertEqual(notice["worstCaseId"], "csn-worst")
        self.assertNotIn(export.RR_4_4_TEXT, notice["caveats"])
        self.assertTrue(any("worst 4 kHz" in c for c in notice["caveats"]))
        self.assertEqual(notice["otherCaseCaveats"], [{"text": export.RR_4_4_TEXT, "cases": 2}])

    def test_rgs_n_worst_case_has_no_scaling_caveat(self):
        notice = self.notices["2"]
        self.assertEqual(notice["worstCaseId"], "rgs-worst")
        self.assertFalse(any("worst 4 kHz" in c for c in notice["caveats"]))
        self.assertEqual([c["cases"] for c in notice["otherCaseCaveats"]], [1])
        self.assertIn("worst 4 kHz", notice["otherCaseCaveats"][0]["text"])

    def test_only_the_governing_row_contributes_caveats(self):
        for notice in self.notices.values():
            self.assertFalse(any("not this row" in c for c in notice["caveats"]))

    def test_rr_4_4_on_other_rows_of_worst_case_is_labelled(self):
        notice = self.notices["3"]
        self.assertNotIn(export.RR_4_4_TEXT, notice["caveats"])
        self.assertIn("does not apply to the headline value", notice["otherCaseCaveats"][0]["text"])

    def test_counts_and_values_come_from_records(self):
        notice = self.notices["1"]
        self.assertEqual(notice["casesOfConcern"], 3)
        self.assertEqual(notice["stationsAffected"], 3)
        self.assertEqual(notice["worstMarginDb"], -42.94)
        self.assertEqual(notice["citation"]["printedPage"], 287)


if __name__ == "__main__":
    unittest.main()


class UsageViewTests(unittest.TestCase):
    def test_regrouping_keeps_every_case_and_skips_border_points(self):
        notices = [
            {"key": "a", "name": "A", "kind": "Space", "stations": [
                {"id": "1", "latitude": 60, "longitude": 25, "finnishBand": "2200 MHz to 2245 MHz", "nationalUse": "primary",
                 "status": "exceeds_limit", "marginDb": -5.0},
                {"id": "2", "latitude": 61, "longitude": 25, "finnishBand": "2200 MHz to 2245 MHz", "nationalUse": "primary",
                 "status": "near_limit", "marginDb": 1.0}]},
            {"key": "b", "name": "B", "kind": "Space", "stations": [
                {"id": "1", "latitude": 60, "longitude": 25, "finnishBand": "3400 MHz to 4200 MHz", "nationalUse": "primary",
                 "status": "exceeds_limit", "marginDb": -9.0}]},
            {"key": "t", "name": "T", "kind": "Terrestrial", "stations": [
                {"id": "Border point", "latitude": 61, "longitude": 30, "band": "793.5 MHz", "status": "exceeds_threshold",
                 "marginDb": -20.0}]},
        ]
        usage = export.usage_views(notices)
        self.assertEqual(sum(b["cases"] for b in usage["bands"]), 4)
        self.assertEqual([b["band"] for b in usage["bands"]], ["793.5 MHz", "3400 MHz to 4200 MHz", "2200 MHz to 2245 MHz"])
        self.assertEqual({s["id"] for s in usage["stations"]}, {"1", "2"})
        station1 = next(s for s in usage["stations"] if s["id"] == "1")
        self.assertEqual((station1["notices"], station1["cases"], station1["worstMarginDb"], station1["worstNoticeKey"]),
                         (2, 2, -9.0, "b"))
        band2200 = next(b for b in usage["bands"] if b["band"].startswith("2200"))
        self.assertEqual((band2200["stations"], band2200["notices"], band2200["statusCounts"]),
                         (2, 1, {"exceeds_limit": 1, "near_limit": 1}))


class TerrestrialCaveatTests(unittest.TestCase):
    """Regression: the above-470 MHz Q&A caveat was attached to 152 MHz assignments too."""

    def test_470_mhz_extension_caveat_only_above_470_mhz(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "brific9999"
            folder.mkdir()
            (folder / "terrestrial_summary.json").write_text(json.dumps({
                "current_issue": 9999, "previous_issue": 9998, "counts": {}, "run_id": "r" * 64,
                "screened_event_count": 2, "finding_count": 2, "assumptions": ["Land path"],
                "criterion": {"title": "ECC T/R 25-08, A.1.2.3", "edition": "2025", "url": "https://example.test",
                              "conditions": {"reference_bandwidth_hz": 25000},
                              "challenge_extension": "Q&A: above-400 MHz value used above 470 MHz."},
            }), encoding="utf-8")
            finding = {"result": "exceeds_threshold", "administration": "RUS", "source_row": 1, "dataset_id": "d" * 64,
                       "field_strength_dbuv_m": 30.0, "threshold_dbuv_m": 20.0, "margin_db": 10.0, "assessments": [],
                       "source_notice": {"stn_cls": "FB"}, "event": "new", "model": {}}
            findings = [dict(finding, assignment_id=1, frequency_mhz=793.5),
                        dict(finding, assignment_id=2, frequency_mhz=152.025, threshold_dbuv_m=12.0)]
            (folder / "terrestrial_brific9999_findings.jsonl").write_text(
                "\n".join(json.dumps(f) for f in findings) + "\n", encoding="utf-8")
            _, notices, _ = export.terrestrial_issue(folder)
        by_id = {n["noticeId"]: n for n in notices}
        self.assertTrue(any("470 MHz" in c for c in by_id["1"]["caveats"]))
        self.assertFalse(any("470 MHz" in c for c in by_id["2"]["caveats"]))
