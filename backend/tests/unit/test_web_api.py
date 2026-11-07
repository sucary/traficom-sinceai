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

from app.web_api import (
    _chat_evidence, _model_messages, _notices_for_request, is_allowed_origin, make_handler,
)


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

    def test_chat_evidence_separates_case_caveats_from_other_cases(self):
        notice = dict(ASSESSMENT["notices"][0], worstCaseId="case-a", priority=1,
                      otherCaseCaveats=[{"text": "Service not allocated (RR No. 4.4)", "cases": 3}])
        evidence = _chat_evidence(notice, {"casesOfConcern": "cases", "stationsAffected": "stations"})

        self.assertEqual(evidence["notice"]["cases_of_concern"], 1)
        self.assertEqual(evidence["notice"]["cases_of_concern_means"], "cases")
        self.assertEqual(evidence["notice"]["priority_rank"], 1)
        self.assertEqual(evidence["worst_case"]["case_id"], "case-a")
        self.assertEqual(evidence["worst_case"]["caveats_for_this_case"], ["Screening result only"])
        self.assertEqual(evidence["worst_case"]["worst_margin_db"], -12.0)
        self.assertNotIn("Service not allocated (RR No. 4.4)", json.dumps(evidence["worst_case"]))
        self.assertEqual(evidence["caveats_on_other_cases_only"][0]["cases"], 3)

    @patch.dict("os.environ", {
        "OPENCODE_API_URL": "https://example.test/chat/completions",
        "OPENCODE_API_KEY": "test-key",
        "OPENCODE_MODEL": "test-model",
    })
    @patch("app.web_api.requests.post")
    def test_chat_streams_contract_events_with_calculated_evidence(self, mock_post):
        model_response = unittest.mock.MagicMock()
        model_response.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"reasoning_content": "Checking notice 123."}}]}',
            "",
            'data: {"choices": [{"delta": {"content": "Notice 123: the recorded margin "}}]}',
            'data: {"choices": [{"delta": {"content": "is -12 dB. Review this case."}}]}',
            "data: [DONE]",
        ]
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
        self.assertNotIn("reasoning", {event["type"] for event in events})
        self.assertEqual(events[0], {"type": "thinking", "text": "Checking notice 123."})
        self.assertEqual([e["text"] for e in events if e["type"] == "text"],
                         ["Notice 123: the recorded margin ", "is -12 dB. Review this case."])
        self.assertEqual(events[-1], {"type": "done"})
        self.assertTrue(mock_post.call_args.kwargs["json"]["stream"])
        self.assertIn({"type": "reference", "ref": "notice:ific3074:123", "label": "ExampleSat notice 123"}, events)
        self.assertIn({"type": "action", "ref": "letter:notice:ific3074:123", "label": "Draft letter for this notice"}, events)
        prompt = mock_post.call_args.kwargs["json"]["messages"]
        self.assertIn('"worst_margin_db":-12.0', prompt[-1]["content"])
        self.assertNotIn("test-key", prompt[-1]["content"])

    def test_cors_allows_local_dev_servers_on_any_port(self):
        for origin in ("http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:4173"):
            self.assertTrue(is_allowed_origin(origin), origin)
        for origin in ("https://localhost:5174", "http://evil.example", "http://localhost.evil.example:5174",
                       "http://localhost", None, ""):
            self.assertFalse(is_allowed_origin(origin), origin)
        response = requests.options(f"{self.base}/chat", headers={"Origin": "http://localhost:5174"}, timeout=5)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "http://localhost:5174")

    def test_invalid_letter_key_returns_404(self):
        response = requests.post(
            f"{self.base}/letters",
            json={"scope": "notice", "key": "ific3074:missing"},
            timeout=5,
        )
        self.assertEqual(response.status_code, 404)


class SelectionCompletenessTests(unittest.TestCase):
    """Regression: a chat about one administration listed 8 of 19 notices as if complete."""

    def test_every_matching_notice_reaches_the_model(self):
        many = [dict(ASSESSMENT["notices"][0], key=f"ific3074:{i}", noticeId=str(i)) for i in range(19)]
        data = dict(ASSESSMENT, notices=many)
        body = {"messages": [{"role": "user", "content": "China"}], "context": {"ref": "administration:CHN"}}
        matched = _notices_for_request(data, body)
        self.assertEqual(len(matched), 19)
        evidence = _model_messages(data, body, matched)[-1]["content"]
        self.assertIn("These 19 record(s) are all notices of concern", evidence)
        self.assertEqual(evidence.count('"notice_id"'), 19)


class PromptSizeAndRetryTests(unittest.TestCase):
    def test_compaction_is_lossless_per_record(self):
        from app.web_api import compact_evidence
        base = ASSESSMENT["notices"][0]
        notices = [
            dict(base, key="a", noticeId="1", caveats=["Common A", "Common B"]),
            dict(base, key="b", noticeId="2", caveats=["Common A", "Common B", "Only this case"]),
            dict(base, key="c", noticeId="3", kind="Terrestrial", assumptions=["Land path"], caveats=["Border caveat"]),
        ]
        records = [_chat_evidence(n) for n in notices]
        compact = compact_evidence(records)
        for original, small in zip(records, compact["records"]):
            kind = original["notice"]["kind"]
            shared = compact["shared_by_kind"][kind]
            rebuilt_caveats = shared["caveats_for_every_worst_case"] + small["worst_case"]["caveats_for_this_case"]
            self.assertEqual(sorted(rebuilt_caveats), sorted(original["worst_case"]["caveats_for_this_case"]))
            assumptions = small["worst_case"].get("assumptions", shared["assumptions"])
            self.assertEqual(assumptions, original["worst_case"]["assumptions"])
            rule = compact["rules"][small["worst_case"]["rule_id"]]
            self.assertEqual(rule["citation"], original["worst_case"]["citation"])
            self.assertEqual(small["caveats_on_other_cases_only"], original["caveats_on_other_cases_only"])
        self.assertEqual(compact["records"][1]["worst_case"]["caveats_for_this_case"], ["Only this case"])

    def test_retry_delay_reads_server_hint(self):
        from app.web_api import retry_delay_seconds
        busy = unittest.mock.MagicMock(headers={}, text="the cell is at capacity; retry shortly (after 30 s)")
        self.assertEqual(retry_delay_seconds(busy), 30)
        self.assertEqual(retry_delay_seconds(unittest.mock.MagicMock(headers={"Retry-After": "5"}, text="")), 5)
        self.assertEqual(retry_delay_seconds(unittest.mock.MagicMock(headers={"Retry-After": "900"}, text="")), 60)

    @patch("app.web_api.time.sleep")
    @patch("app.web_api.requests.post")
    def test_busy_model_is_retried_then_streams(self, mock_post, mock_sleep):
        from app.web_api import _stream_completion
        busy = unittest.mock.MagicMock(status_code=429, headers={}, text="at capacity (after 30 s)")
        busy.raise_for_status.side_effect = requests.HTTPError(response=busy)
        ok = unittest.mock.MagicMock()
        ok.iter_lines.return_value = ['data: {"choices": [{"delta": {"content": "Answer"}}]}', "data: [DONE]"]
        mock_post.side_effect = [busy, ok]
        pieces = list(_stream_completion([], "https://example.test", "key", "model"))
        self.assertEqual(pieces[0][0], "thinking")
        self.assertIn("retrying in 30 s", pieces[0][1])
        self.assertEqual(pieces[-1], ("text", "Answer"))
        mock_sleep.assert_called_once_with(30)

    @patch("app.web_api.time.sleep")
    @patch("app.web_api.requests.post")
    def test_gives_up_after_retries(self, mock_post, mock_sleep):
        from app.web_api import MODEL_RETRIES, _stream_completion
        busy = unittest.mock.MagicMock(status_code=429, headers={}, text="at capacity (after 1 s)")
        busy.raise_for_status.side_effect = requests.HTTPError(response=busy)
        mock_post.return_value = busy
        with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
            list(_stream_completion([], "https://example.test", "key", "model"))
        self.assertEqual(mock_post.call_count, MODEL_RETRIES + 1)


class StreamEncodingTests(unittest.TestCase):
    @patch("app.web_api.requests.post")
    def test_utf8_characters_survive_event_stream_without_charset(self, mock_post):
        import io
        from app.web_api import _stream_completion
        response = requests.models.Response()
        response.status_code = 200
        response.headers["Content-Type"] = "text/event-stream"  # no charset, as OpenCode sends it
        response.encoding = requests.utils.get_encoding_from_headers(response.headers)  # ISO-8859-1
        payload = json.dumps({"choices": [{"delta": {"content": "PFD -95.06 dB(W/m²), 40 dB(µV/m)"}}]}, ensure_ascii=False)
        response.raw = io.BytesIO(f"data: {payload}\n\ndata: [DONE]\n\n".encode("utf-8"))
        mock_post.return_value = response
        text = "".join(piece for kind, piece in _stream_completion([], "https://example.test", "key", "m") if kind == "text")
        self.assertEqual(text, "PFD -95.06 dB(W/m²), 40 dB(µV/m)")
        self.assertNotIn("Â", text)


class UsageViewTests(unittest.TestCase):
    def test_usage_questions_get_the_usage_view(self):
        from app.web_api import wants_usage_view
        ask = lambda text, ref=None: {"messages": [{"role": "user", "content": text}], "context": {"ref": ref} if ref else {}}
        self.assertTrue(wants_usage_view(ask("Which Finnish band is most affected?")))
        self.assertTrue(wants_usage_view(ask("Tell me more", "station:408577")))
        self.assertFalse(wants_usage_view(ask("Which notices need attention first?")))

    def test_usage_summary_is_added_with_station_total(self):
        stations = [{"id": str(i), "worstMarginDb": -1.0} for i in range(40)]
        data = dict(ASSESSMENT, usage={"definitions": {"band": "M4 band"}, "bands": [{"band": "2200 MHz to 2245 MHz"}],
                                       "stations": stations})
        body = {"messages": [{"role": "user", "content": "Which station is most affected?"}]}
        messages = _model_messages(data, body, data["notices"])
        usage = messages[-1]["content"]
        self.assertIn("30 most affected of 40", usage)
        self.assertIn("2200 MHz to 2245 MHz", usage)


class FunnelTests(unittest.TestCase):
    def test_issue_funnel_reaches_the_model(self):
        funnel = [{"stage": "Notices published in the IFIC", "count": 196},
                  {"stage": "Notices of concern", "count": 60}]
        data = dict(ASSESSMENT, issues=[dict(ASSESSMENT["issues"][0], funnel=funnel)])
        body = {"messages": [{"role": "user", "content": "How many notices are there?"}]}
        content = _model_messages(data, body, data["notices"])[-1]["content"]
        self.assertIn('"IFIC 3074":[{"stage":"Notices published in the IFIC","count":196}', content)
        self.assertIn("notices of concern", content)
