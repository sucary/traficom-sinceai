import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from scripts.explain_risks import (
    explain_with_model,
    satellite_notice_summaries,
    terrestrial_summaries,
)


class RiskExplanationInputTests(unittest.TestCase):
    def write_jsonl(self, directory, name, records):
        path = Path(directory) / name
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def satellite_record(self, notice_id, status, margin):
        return {
            "space": {"notice_id": notice_id, "administration": "CHN"},
            "satellite_names": ["Example"],
            "finnish_station": {
                "station_number": "123",
                "protected_band": {"frequency_min_hz": 3_500_000_000, "frequency_max_hz": 3_600_000_000},
            },
            "frequency_relation": "co_frequency",
            "evaluations": [{
                "criterion_id": "criterion",
                "caveats": ["conservative assumption"],
                "sharing": {"article5_region1": [{"result": "equal_rights"}]},
            }],
            "result": {
                "status": status,
                "worst_margin_db": margin,
                "governing_criterion_id": "criterion",
                "governing_applicability": "applicable",
                "pfd_db": -100,
                "limit_db": -120,
                "reference_bandwidth_hz": 1_000_000,
                "regulation_citation": {"provision": "RR Table 21-4", "printed_page": 287},
            },
        }

    def test_satellite_cases_are_grouped_and_ordered_by_worst_margin(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_jsonl(temporary, "space.jsonl", [
                self.satellite_record(1, "near_limit", 2),
                self.satellite_record(1, "exceeds_limit", -5),
                self.satellite_record(2, "exceeds_limit", -12),
                self.satellite_record(3, "below_limit", 8),
            ])
            summaries = satellite_notice_summaries(path, 2)

        self.assertEqual([item["notice_id"] for item in summaries], [2, 1])
        self.assertEqual(summaries[1]["review_case_count_for_notice"], 2)
        self.assertEqual(summaries[1]["margin_db"], -5)
        self.assertEqual(summaries[1]["article5_sharing_results"], ["equal_rights"])

    def test_terrestrial_exceedances_are_sorted_by_margin(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_jsonl(temporary, "land.jsonl", [
                {"result": "below_threshold", "margin_db": -2},
                {"result": "exceeds_threshold", "margin_db": 4, "frequency_mhz": 150},
                {"result": "exceeds_threshold", "margin_db": 15, "frequency_mhz": 800},
            ])
            summaries = terrestrial_summaries(path, 1)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["frequency_mhz"], 800)
        self.assertEqual(summaries[0]["margin_db"], 15)

    @patch("scripts.explain_risks.requests.post")
    def test_model_explanation_uses_configured_chat_endpoint(self, mock_post):
        response = unittest.mock.MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "Review this case."}}]}
        mock_post.return_value = response

        explanation = explain_with_model(
            {"status": "exceeds_limit"},
            "https://example.test",
            "secret",
            "model",
        )

        self.assertEqual(explanation, "Review this case.")
        self.assertEqual(mock_post.call_args.args[0], "https://example.test")
        self.assertEqual(mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer secret")

    @patch("scripts.explain_risks.requests.post")
    def test_cloudflare_403_explains_block_reason(self, mock_post):
        response = requests.Response()
        response.status_code = 403
        response._content = b"error code: 1010"
        error = requests.HTTPError(response=response)
        mock_post.return_value.raise_for_status.side_effect = error
        mock_post.return_value.status_code = 403
        mock_post.return_value.text = "error code: 1010"

        with self.assertRaisesRegex(RuntimeError, "Cloudflare error 1010"):
            explain_with_model({"status": "exceeds_limit"}, "https://example.test", "secret", "model")
