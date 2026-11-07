"""HTTP API for the assessment frontend."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

from .config import PROJECT_ROOT


ASSESSMENT_PATH = PROJECT_ROOT / "frontend" / "public" / "data" / "assessment.json"
EXPORT_SCRIPT = PROJECT_ROOT / "backend" / "scripts" / "export_frontend_data.py"
CORS_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
}


def load_assessment(path=ASSESSMENT_PATH):
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Assessment export not found at {path}; run the assessment export before starting the API"
        ) from error
    if not isinstance(data, dict) or not all(
        isinstance(data.get(field), list) for field in ("issues", "notices", "trends")
    ):
        raise ValueError(f"Assessment export has an invalid shape: {path}")
    return data


def notifications_for(data):
    items = []
    for issue in data["issues"]:
        items.append({
            "id": f"ready:{issue['id']}",
            "text": f"[{issue['label']}](issue:{issue['id']}) results are ready with "
                    f"{issue['noticesOfConcern']} notices of concern",
            "ref": f"issue:{issue['id']}",
        })
        top = next((notice for notice in data["notices"] if notice["issueId"] == issue["id"]), None)
        if top:
            items.append({
                "id": f"top:{top['key']}",
                "text": f"[{top['name']}](notice:{top['key']}) from "
                        f"[{top['administrationName']}](administration:{top['administration']}) "
                        f"is {top['status'].replace('_', ' ')}",
                "ref": f"notice:{top['key']}",
            })
    return items


def _letter_paragraph(notice, index, issues):
    issue_label = next((item["label"] for item in issues if item["id"] == notice["issueId"]), notice["issueId"])
    if notice["kind"] == "Space":
        quantity = "power flux density"
        heading = (
            f"{index}. Notice {notice['noticeId']}, {notice['name']}, {notice['provision']}, "
            f"{issue_label}"
        )
    else:
        quantity = "field strength at the Finnish border"
        heading = (
            f"{index}. Assignment {notice['noticeId']}, {notice['name']}, {notice['provision']}, "
            f"{issue_label}"
        )
    citation = ", ".join(filter(None, (notice.get("rule", {}).get("id"), notice.get("citation", {}).get("provision"))))
    return (
        f"{heading}\n\nThe screening result is {notice.get('value')} {notice.get('unit')} against "
        f"{notice.get('limit')} {notice.get('unit')} ({citation}). The recorded status is "
        f"{notice['status'].replace('_', ' ')} with a margin of {notice.get('worstMarginDb')} dB. "
        f"{notice.get('stationsAffected', 0)} Finnish stations or assessment points are affected."
    )


def draft_letter(data, scope, key):
    if scope == "notice":
        notices = [notice for notice in data["notices"] if notice["key"] == key]
    elif scope == "administration":
        notices = [notice for notice in data["notices"] if notice["administration"] == key]
    else:
        raise ValueError("scope must be 'notice' or 'administration'")
    if not notices:
        raise KeyError(f"No assessment notice matches {scope} {key!r}")

    first = notices[0]
    paragraphs = "\n\n".join(
        _letter_paragraph(notice, index, data["issues"])
        for index, notice in enumerate(notices, 1)
    )
    return (
        "Finnish Transport and Communications Agency Traficom\n\n"
        f"To the Administration of {first['administrationName']} ({first['administration']})\n\n"
        f"Subject: Comments on {len(notices)} filing(s) published in the ITU International "
        "Frequency Information Circular\n\n"
        "Dear Colleagues,\n\n"
        "Traficom has reviewed the filings listed below against the protection of Finnish radio "
        "stations. These are deterministic screening results and reasons for expert review, not "
        "proof of harmful interference.\n\n"
        f"{paragraphs}\n\n"
        "We kindly ask your Administration to confirm the technical parameters of these filings "
        "and take the protection of Finnish stations into account. We are ready to discuss these results.\n\n"
        "Yours sincerely,\n\nSpectrum Management\nFinnish Transport and Communications Agency Traficom"
    )


def _notices_for_request(data, request_body):
    notices = data["notices"]
    context_ref = (request_body.get("context") or {}).get("ref", "")
    if context_ref.startswith("notice:"):
        key = context_ref[len("notice:"):]
        return [notice for notice in notices if notice["key"] == key]
    if context_ref.startswith("administration:"):
        code = context_ref.split(":", 1)[1]
        matched = [notice for notice in notices if notice["administration"] == code]
        return matched[:8]
    if context_ref.startswith("station:"):
        station_id = context_ref.split(":", 1)[1]
        matched = [notice for notice in notices if any(s["id"] == station_id for s in notice.get("stations", []))]
        return matched[:8]
    if context_ref.startswith("issue:"):
        issue_id = context_ref.split(":", 1)[1]
        matched = [notice for notice in notices if notice["issueId"] == issue_id]
        return matched[:8]

    query = request_body["messages"][-1]["content"].lower()
    tokens = set(re.findall(r"[a-z0-9]+", query))
    for notice in notices:
        if notice["noticeId"].lower() in tokens or notice["name"].lower() in query:
            return [notice]
    for notice in notices:
        if notice["administration"].lower() in tokens or notice["administrationName"].lower() in query:
            matched = [item for item in notices if item["administration"] == notice["administration"]]
            return matched[:8]
    for notice in notices:
        if any(station["id"] in tokens for station in notice.get("stations", [])):
            station_ids = {station["id"] for station in notice.get("stations", []) if station["id"] in tokens}
            return [
                item for item in notices
                if any(station["id"] in station_ids for station in item.get("stations", []))
            ][:8]
    if any(word in query for word in ("first", "priority", "overview", "summary", "risk", "notice")):
        return notices[:8]
    return notices[:5]


def _chat_evidence(notice):
    return {
        "notice_rollup": {
            "key": notice["key"],
            "issue": notice["issueId"],
            "kind": notice["kind"],
            "notice_id": notice["noticeId"],
            "administration": notice["administrationName"],
            "name": notice["name"],
            "affected_stations": notice.get("stationsAffected"),
            "cases_of_concern": notice.get("casesOfConcern"),
            "caveats_across_notice_cases": notice.get("caveats", []),
        },
        "worst_case_in_rollup": {
            "status": notice["status"],
            "worst_margin_db": notice.get("worstMarginDb"),
            "quantity": notice.get("measure"),
            "value": notice.get("value"),
            "unit": notice.get("unit"),
            "limit": notice.get("limit"),
            "reference_bandwidth": notice.get("referenceBandwidth"),
            "protected_band": notice.get("band"),
            "rule": notice.get("rule"),
            "citation": notice.get("citation"),
            "assumptions": notice.get("assumptions", []),
        },
    }


def _completion(data, request_body, api_url, api_key, model, notices):
    messages = [{
        "role": "system",
        "content": (
            "You are a careful spectrum assessment assistant for Traficom. Use only the assessment "
            "evidence supplied below and the user's conversation. Never calculate or alter values. "
            "A screening exceedance is a reason for expert review, not proof of harmful interference "
            "or a regulatory violation. Clearly distinguish calculated facts from assumptions and "
            "limitations. Evidence contains notice rollups and a separate worst case within each "
            "rollup. The rollup caveats may belong to other cases in the same notice; do not imply "
            "they all apply to the reported worst case. Cite the supplied rule and page where "
            "available. Keep the answer concise, use the UI's supported Markdown, and do not use "
            "em dashes, vertical bars, or separator hyphens. When referring to notices, include "
            "their notice or assignment ID."
        ),
    }]
    messages.extend(request_body["messages"][-12:])
    messages.append({
        "role": "system",
        "content": "Relevant calculated assessment records (authoritative values; do not recompute):\n"
                   + json.dumps([_chat_evidence(n) for n in notices], ensure_ascii=False),
    })
    try:
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "x-opencode-session": "traficom-frontend-chat"},
            json={"model": model, "messages": messages},
            timeout=90,
        )
        response.raise_for_status()
        body = response.json()
    except requests.RequestException as error:
        detail = ""
        if isinstance(error, requests.HTTPError) and error.response is not None:
            detail = error.response.text.strip().replace(api_key, "[redacted]")[:300]
            detail = f" HTTP {error.response.status_code}: {detail}"
        raise RuntimeError(f"Model request failed.{detail}") from error
    except requests.JSONDecodeError as error:
        raise RuntimeError("Model returned invalid JSON") from error
    try:
        answer = body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise RuntimeError("Model response did not contain a chat answer") from error
    return answer, notices


def _chat_events(data, request_body):
    api_url = os.getenv("OPENCODE_API_URL")
    api_key = os.getenv("OPENCODE_API_KEY")
    model = os.getenv("OPENCODE_MODEL", "opencode/big-pickle")
    if not api_url or not api_key:
        yield {"type": "error", "message": "Configure OPENCODE_API_URL and OPENCODE_API_KEY on the backend."}
        return

    notices = _notices_for_request(data, request_body)
    yield {"type": "reasoning", "text": f"Loaded {len(notices)} relevant calculated assessment record(s)."}
    yield {"type": "reasoning", "text": "Using the recorded values, statuses, assumptions, and citations without recalculating them."}
    try:
        answer, notices = _completion(data, request_body, api_url, api_key, model, notices)
    except RuntimeError as error:
        yield {"type": "error", "message": str(error)}
        return

    chunk_size = 30
    for offset in range(0, len(answer), chunk_size):
        yield {"type": "text", "text": answer[offset:offset + chunk_size]}

    seen = set()
    for notice in notices:
        ref = f"notice:{notice['key']}"
        if ref not in seen:
            yield {"type": "reference", "ref": ref, "label": f"{notice['name']} notice {notice['noticeId']}"}
            seen.add(ref)
        if notice.get("citation", {}).get("url"):
            citation_ref = notice["citation"]["url"]
            if citation_ref not in seen:
                yield {"type": "reference", "ref": citation_ref, "label": notice["citation"]["document"]}
                seen.add(citation_ref)

    if notices:
        first = notices[0]
        yield {
            "type": "action",
            "ref": f"notice:{first['key']}",
            "label": f"Open {first['name']}",
        }
        yield {
            "type": "action",
            "ref": f"letter:notice:{first['key']}",
            "label": "Draft letter for this notice",
        }
        yield {
            "type": "action",
            "ref": f"administration:{first['administration']}",
            "label": f"All notices from {first['administrationName']}",
        }
    yield {"type": "done"}


def _validate_chat_request(body):
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list) or not body["messages"]:
        raise ValueError("messages must be a non-empty array")
    if len(body["messages"]) > 40:
        raise ValueError("messages must contain at most 40 entries")
    for message in body["messages"]:
        if (
            not isinstance(message, dict)
            or message.get("role") not in {"user", "assistant"}
            or not isinstance(message.get("content"), str)
        ):
            raise ValueError("each message must have role 'user' or 'assistant' and string content")
        if len(message["content"]) > 12000:
            raise ValueError("message content must be at most 12000 characters")
    if not body["messages"][-1]["content"].strip():
        raise ValueError("the last message cannot be empty")
    context = body.get("context", {})
    if context is not None and not isinstance(context, dict):
        raise ValueError("context must be an object")


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def make_handler(assessment_path=ASSESSMENT_PATH):
    class AssessmentHandler(BaseHTTPRequestHandler):
        server_version = "TraficomAssessment/1.0"

        def log_message(self, format_string, *args):
            return

        def _headers(self, status, content_type, length=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            origin = self.headers.get("Origin")
            if origin in CORS_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
            self.send_header("Cache-Control", "no-store")
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.end_headers()

        def _json(self, status, value):
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(payload))
            self.wfile.write(payload)

        def _read_json(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("invalid Content-Length") from error
            if length <= 0 or length > 1_000_000:
                raise ValueError("request body must be between 1 byte and 1 MB")
            try:
                return json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ValueError("request body must be valid JSON") from error

        def do_OPTIONS(self):
            self._headers(204, "application/json", 0)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/health":
                self._json(200, {"status": "ok"})
                return
            if path not in {"/api/assessment", "/api/notifications"}:
                self._json(404, {"error": "Not found"})
                return
            try:
                assessment = load_assessment(assessment_path)
                result = assessment if path == "/api/assessment" else notifications_for(assessment)
                self._json(200, result)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                self._json(503, {"error": str(error)})

        def do_POST(self):
            path = urlsplit(self.path).path
            if path not in {"/api/letters", "/api/chat"}:
                self._json(404, {"error": "Not found"})
                return
            try:
                body = self._read_json()
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
                assessment = load_assessment(assessment_path)
                if path == "/api/letters":
                    scope, key = body.get("scope"), body.get("key")
                    if not isinstance(key, str) or not key:
                        raise ValueError("key must be a non-empty string")
                    text = draft_letter(assessment, scope, key)
                    self._json(200, {"text": text})
                    return

                _validate_chat_request(body)
                self._headers(200, "application/x-ndjson; charset=utf-8")
                for event in _chat_events(assessment, body):
                    self.wfile.write(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()
            except ValueError as error:
                self._json(400, {"error": str(error)})
            except KeyError as error:
                self._json(404, {"error": str(error)})
            except (OSError, json.JSONDecodeError) as error:
                self._json(503, {"error": str(error)})

    return AssessmentHandler


def serve(host="127.0.0.1", port=8000, export=True):
    load_dotenv(PROJECT_ROOT / ".env")
    if export:
        subprocess.run([sys.executable, str(EXPORT_SCRIPT)], cwd=PROJECT_ROOT, check=True)
    server = _Server((host, port), make_handler())
    print(f"Assessment API listening on http://{host}:{server.server_port}/api")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-export", action="store_true", help="Use the existing assessment.json without rebuilding it")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    serve(args.host, args.port, export=not args.no_export)
    return 0
