import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import requests

from app.web_api import _chat_evidence, make_handler


ASSESSMENT = {
    "generated": "7 November 2026",
    "issues": [{
        "id": "ific3074",
        "label": "IFIC 3074",
        "noticesOfConcern": 1,
        "kind": "Space",
        "counts": {},
        "runId": "run",
    }],
    "notices": [{
        "key": "ific3074:123",
        "issueId": "ific3074",
        "kind": "Space",
        "noticeId": "123",
        "administration": "CHN",
        "administrationName": "China",
        "name": "ExampleSat",
        "provision": "9.1 advance publication",
        "publicationDate": "1 June 2026",
        "status": "exceeds_limit",
        "worstMarginDb": -12.0,
        "measure": "PFD",
        "unit": "dB(W/m²)",
        "value": -100.0,
        "limit": -112.0,
        "referenceBandwidth": "1 MHz",
        "elevationDeg": 5.0,
        "band": "3.4 to 4.2 GHz",
        "rule": {"id": "criterion-1", "text": "Criterion text"},
        "citation": {
            "document": "Radio Regulations",
            "provision": "Article 21",
            "printedPage": 287,
            "pdfPage": 297,
            "url": "https://example.test/rules.pdf",
        },
        "assumptions": ["Peak beam gain assumed"],
        "caveats": ["Screening result only"],
        "stationsAffected": 1,
        "casesOfConcern": 1,
        "stations": [{
            "id": "987654",
            "latitude": 60,
            "longitude": 25,
            "band": "3.4 to 4.2 GHz",
            "status": "exceeds_limit",
            "value": -100.0,
            "limit": -112.0,
            "marginDb": -12.0,
        }],
        "sourceRows": [],
    }],
    "trends": [],
}


class FrontendApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.assessment_path = Path(self.temporary.name) / "assessment.json"
        self.assessment_path.write_text(json.dumps(ASSESSMENT), encoding="utf-8")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.assessment_path),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/api"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def test_assessment_and_notifications_endpoints(self):
        response = requests.get(f"{self.base}/assessment", timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notices"][0]["noticeId"], "123")

        response = requests.get(f"{self.base}/notifications", timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[1]["ref"], "notice:ific3074:123")

    def test_letter_endpoint_accepts_notice_key(self):
        response = requests.post(
            f"{self.base}/letters",
            json={"scope": "notice", "key": "ific3074:123"},
            timeout=5,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Notice 123", response.json()["text"])
        self.assertIn("expert review", response.json()["text"])

    def test_chat_evidence_separates_rollup_caveats_from_worst_case(self):
        evidence = _chat_evidence(ASSESSMENT["notices"][0])

        self.assertEqual(evidence["notice_rollup"]["cases_of_concern"], 1)
        self.assertEqual(
            evidence["notice_rollup"]["caveats_across_notice_cases"],
            ["Screening result only"],
        )
        self.assertEqual(evidence["worst_case_in_rollup"]["status"], "exceeds_limit")
        self.assertEqual(evidence["worst_case_in_rollup"]["worst_margin_db"], -12.0)

    @patch.dict("os.environ", {
        "OPENCODE_API_URL": "https://example.test/chat/completions",
        "OPENCODE_API_KEY": "test-key",
        "OPENCODE_MODEL": "test-model",
    })
    @patch("app.web_api.requests.post")
    def test_chat_streams_contract_events_with_calculated_evidence(self, mock_post):
        model_response = unittest.mock.MagicMock()
        model_response.json.return_value = {
            "choices": [{"message": {"content": "The recorded margin is -12 dB. Review this case."}}]
        }
        mock_post.return_value = model_response

        url = urlsplit(self.base)
        connection = HTTPConnection(url.hostname, url.port, timeout=5)
        connection.request(
            "POST",
            f"{url.path}/chat",
            body=json.dumps({
                "conversationId": "conversation",
                "messages": [{"role": "user", "content": "Explain this notice"}],
                "context": {"ref": "notice:ific3074:123"},
            }),
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        )
        response = connection.getresponse()
        response_body = response.read().decode("utf-8")
        connection.close()

        events = [json.loads(line) for line in response_body.splitlines()]
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/x-ndjson; charset=utf-8")
        self.assertEqual(events[0]["type"], "reasoning")
        self.assertEqual(events[-1], {"type": "done"})
        self.assertIn({"type": "reference", "ref": "notice:ific3074:123", "label": "ExampleSat notice 123"}, events)
        self.assertIn({"type": "action", "ref": "letter:notice:ific3074:123", "label": "Draft letter for this notice"}, events)
        prompt = mock_post.call_args.kwargs["json"]["messages"]
        self.assertIn('"worst_margin_db": -12.0', prompt[-1]["content"])
        self.assertNotIn("test-key", prompt[-1]["content"])

    def test_invalid_letter_key_returns_404(self):
        response = requests.post(
            f"{self.base}/letters",
            json={"scope": "notice", "key": "ific3074:missing"},
            timeout=5,
        )
        self.assertEqual(response.status_code, 404)
