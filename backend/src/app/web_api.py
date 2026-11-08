import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import requests
from dotenv import load_dotenv

from .analysis_jobs import Jobs, receive_upload
from .config import PROJECT_ROOT


ASSESSMENT_PATH = PROJECT_ROOT / "frontend" / "public" / "data" / "assessment.json"
EXPORT_SCRIPT = PROJECT_ROOT / "backend" / "scripts" / "export_frontend_data.py"
LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1):\d{1,5}$")


def is_allowed_origin(origin):
    return bool(origin) and LOCAL_ORIGIN.fullmatch(origin) is not None


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


SPACE_WORDS = ("satellite", "space", "pfd", "table 21-4", "gso", "orbit")
SPACE_ISSUE = re.compile(r"(?<!br )(?<!br)\bific ?\d{4}")
TERRESTRIAL_WORDS = ("terrestrial", "land mobile", "land-mobile", "border", "field strength", "t/r 25-08",
                     "p.1546", "brific", "br ific")
TREND_WORDS = ("trend", "anomal", "activity", "neighbour", "neighbor", "changed", "new filings", "over time")
FRAMEWORK_WORDS = ("rule", "regulation", "framework", "provision", "legal", "article", "m4")


def _issue_number(issue):
    digits = re.sub(r"\D", "", issue.get("id", ""))
    return int(digits) if digits else 0


def route_request(data, request_body):
    issues = data.get("issues", [])
    kinds = {"Space": "space", "Terrestrial": "terrestrial"}
    query = request_body["messages"][-1]["content"].lower()
    ref = (request_body.get("context") or {}).get("ref", "") or ""

    context_issue = None
    if ref.startswith("issue:"):
        context_issue = ref.split(":", 1)[1]
    elif ref.startswith("notice:"):
        context_issue = ref[len("notice:"):].split(":", 1)[0]

    named = [i for i in issues if str(_issue_number(i)) in re.findall(r"\b\d{4}\b", query)]
    space = any(word in query for word in SPACE_WORDS) or bool(SPACE_ISSUE.search(query))
    terrestrial = any(word in query for word in TERRESTRIAL_WORDS)
    wants_trends = any(word in query for word in TREND_WORDS)
    wants_framework = any(word in query for word in FRAMEWORK_WORDS)

    if context_issue and any(i["id"] == context_issue for i in issues):
        selected = [i for i in issues if i["id"] == context_issue]
        reason = "the issue of the page the question was asked from"
    elif named:
        selected = named
        reason = "the issue named in the question"
    else:
        domains = [k for k, flag in (("Space", space), ("Terrestrial", terrestrial)) if flag] or list(kinds)
        pool = [i for i in issues if i.get("kind") in domains]
        if wants_trends:
            selected = pool
            reason = "all issues, for a trend question"
        else:
            selected = [max((i for i in pool if i.get("kind") == k), key=_issue_number)
                        for k in domains if any(i.get("kind") == k for i in pool)]
            reason = "the latest issue of each selected domain"
    reasons = [reason]
    named_ids = set(re.findall(r"\b\d{6,}\b", query))
    notice_issues = {n.get("issueId") for n in data.get("notices", []) if str(n.get("noticeId")) in named_ids}
    for issue in issues:
        if issue["id"] in notice_issues and issue not in selected:
            selected.append(issue)
            reasons.append(f"{issue.get('label', issue['id'])} for the notice named in the question")
    for kind, flag in (("Space", space), ("Terrestrial", terrestrial)):
        if flag and not any(i.get("kind") == kind for i in selected):
            candidates = [i for i in issues if i.get("kind") == kind]
            if candidates:
                latest = max(candidates, key=_issue_number)
                selected.append(latest)
                reasons.append(f"{latest.get('label', latest['id'])} as the latest {kind.lower()} issue the question asks about")
    reason = "; ".join(reasons)
    ids = [i["id"] for i in selected]
    labels = ", ".join(f"{i.get('label', i['id'])} ({i.get('kind', '')})" for i in selected)
    return {
        "issue_ids": ids,
        "wants_trends": wants_trends,
        "wants_framework": wants_framework,
        "frameworks": {i.get("label", i["id"]): i["regulatoryFramework"]
                       for i in issues if i.get("regulatoryFramework")},
        "note": f"Scope: {labels or 'no issue'}, selected as {reason}. Mention this scope when it matters, and "
                "keep space and terrestrial results in separate tables.",
    }


def scoped_data(data, scope):
    ids = set(scope["issue_ids"])
    return {**data,
            "notices": [n for n in data.get("notices", []) if n.get("issueId") in ids],
            "issues": [i for i in data.get("issues", []) if i.get("id") in ids],
            "trends": [t for t in data.get("trends", []) if t.get("issueId") in ids]}


def _notices_for_request(data, request_body):
    notices = data["notices"]
    context_ref = (request_body.get("context") or {}).get("ref", "")
    if context_ref.startswith("notice:"):
        key = context_ref[len("notice:"):]
        return [notice for notice in notices if notice["key"] == key]
    if context_ref.startswith("administration:"):
        code = context_ref.split(":", 1)[1]
        return [notice for notice in notices if notice["administration"] == code]
    if context_ref.startswith("station:"):
        station_id = context_ref.split(":", 1)[1]
        return [notice for notice in notices if any(s["id"] == station_id for s in notice.get("stations", []))]
    if context_ref.startswith("issue:"):
        issue_id = context_ref.split(":", 1)[1]
        return [notice for notice in notices if notice["issueId"] == issue_id]

    query = request_body["messages"][-1]["content"].lower()
    tokens = set(re.findall(r"[a-z0-9]+", query))
    for notice in notices:
        if notice["noticeId"].lower() in tokens or notice["name"].lower() in query:
            return [notice]
    for notice in notices:
        if notice["administration"].lower() in tokens or notice["administrationName"].lower() in query:
            return [item for item in notices if item["administration"] == notice["administration"]]
    for notice in notices:
        if any(station["id"] in tokens for station in notice.get("stations", [])):
            station_ids = {station["id"] for station in notice.get("stations", []) if station["id"] in tokens}
            return [
                item for item in notices
                if any(station["id"] in station_ids for station in item.get("stations", []))
            ]
    return list(notices)


def _chat_evidence(notice, definitions=None):
    definitions = definitions or {}
    return {
        "notice": {
            "key": notice["key"],
            "priority_rank": notice.get("priority"),
            "issue": notice["issueId"],
            "kind": notice["kind"],
            "notice_id": notice["noticeId"],
            "administration": notice["administrationName"],
            "name": notice["name"],
            "provision": notice.get("provision"),
            "response_deadline": notice.get("responseDeadline"),
            "cases_of_concern": notice.get("casesOfConcern"),
            "cases_of_concern_means": definitions.get("casesOfConcern"),
            "stations_affected": notice.get("stationsAffected"),
            "stations_affected_means": definitions.get("stationsAffected"),
        },
        "worst_case": {
            "case_id": notice.get("worstCaseId"),
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
            "caveats_for_this_case": notice.get("caveats", []),
        },
        "caveats_on_other_cases_only": notice.get("otherCaseCaveats", []),
    }


SYSTEM_PROMPT = (
    "You are a careful spectrum assessment assistant for Traficom. Use only the assessment "
    "evidence supplied below and the user's conversation. Never calculate or alter values. "
    "A screening exceedance is a reason for expert review, not proof of harmful interference "
    "or a regulatory violation. Clearly distinguish calculated facts from assumptions and "
    "limitations. Each record has a worst_case with its own caveats_for_this_case; only those caveats "
    "describe the reported values. caveats_on_other_cases_only belong to other cases of the "
    "same notice: never attach them to the worst case, and if you mention one, say it applies "
    "to other cases. Present notices in the supplied priority_rank order; do not re-rank. "
    "When giving counts, say whether they are cases or distinct stations. If you list only some "
    "of the supplied notices, say how many of how many you list. Cite the supplied rule and page "
    "where available. When referring to notices, include their notice or assignment ID. The supplied "
    "records are notices of concern only, not every notice in the data: call them notices of concern, "
    "and use issue_funnels for totals such as how many notices were published, matched or calculated. "
    "A notice's response_deadline is the last day Finland can comment (RR No. 9.3, advance publication) or "
    "state disagreement (RR No. 9.52, coordination request): four months after the IFIC publication date; "
    "notifications (No. 11.2) have none. "
    "The terrestrial threshold is this assessment's screening criterion (T/R 25-08, extended above 470 MHz "
    "per the challenge Q&A); do not present it as the coordination rule other bands or systems are bound by.\n\n"
    "How to answer: write like an experienced colleague, not a report generator. Let the question decide "
    "the shape and length of the answer.\n"
    "- Answer the question in the first sentence. A simple question gets a short answer, often a few "
    "sentences with no headings or lists.\n"
    "- Use a table only when it genuinely helps, such as comparing several notices; choose only the "
    "columns the question needs. Use lists for a handful of separate facts, prose otherwise.\n"
    "- Mention only the caveats and limitations that matter for this answer, briefly and where they "
    "apply. Do not repeat the standard assumptions every time, but always make clear that an exceedance "
    "is a reason for review, not proof of interference, when the answer is about risk or interference.\n"
    "- Mention the scope or funnel totals only when they help the answer, for example when asked about an "
    "issue, about totals, or when the scope might surprise the user.\n"
    "- In a follow-up, do not repeat what was already said; build on it.\n"
    "- Link notices as [name notice_id](notice:<key>), using the record's key.\n"
    "- A margin is the difference from the limit or threshold, never the PFD or field-strength value itself; "
    "take it from the margin fields. Terrestrial results have a threshold, space results a limit.\n"
    "- Never write a margin as a signed number: say '42.94 dB over the limit' or '4.46 dB below the "
    "threshold', so its direction is unmistakable.\n"
    "- Describe notices only with attributes the records give (do not infer a service or system type).\n"
    "- When nothing in the evidence matches the question, say so briefly, say what the evidence does not "
    "cover, and stop. Do not guess whether unsupplied records exist or what happened to them, and do not "
    "pad the answer with items that do not actually match (for example a different frequency range).\n"
    "Markdown the UI renders: paragraphs, #### headings, '- ' and '1. ' lists, tables, **bold**, "
    "[label](ref) links. Do not use em dashes, and use vertical bars only inside tables."
)


def compact_evidence(records):
    by_kind = {}
    for record in records:
        by_kind.setdefault(record["notice"]["kind"], []).append(record["worst_case"])
    shared = {}
    for kind, cases in by_kind.items():
        first = cases[0]
        shared[kind] = {
            "assumptions": first["assumptions"] if all(c["assumptions"] == first["assumptions"] for c in cases) else [],
            "caveats_for_every_worst_case": [c for c in first["caveats_for_this_case"]
                                             if all(c in other["caveats_for_this_case"] for other in cases)],
        }
    rules, compact = {}, []
    for record in records:
        kind_shared = shared[record["notice"]["kind"]]
        case = dict(record["worst_case"])
        rule, citation = case.pop("rule") or {}, case.pop("citation") or {}
        rule_id = rule.get("id") or ""
        rules.setdefault(rule_id, {"text": rule.get("text"), "citation": citation})
        case["rule_id"] = rule_id
        if kind_shared["assumptions"]:
            case.pop("assumptions")
        case["caveats_for_this_case"] = [c for c in case["caveats_for_this_case"]
                                         if c not in kind_shared["caveats_for_every_worst_case"]]
        compact.append({**record, "worst_case": case})
    return {"shared_by_kind": shared, "rules": rules, "records": compact}


def _model_messages(data, request_body, notices, scope=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(request_body["messages"][-12:])
    evidence = compact_evidence([_chat_evidence(n, data.get("countDefinitions")) for n in notices])
    messages.append({
        "role": "system",
        "content": (scope["note"] + "\n" if scope else "")
                   + "issue_funnels (notice counts per stage for each issue): "
                   + json.dumps({i.get("label", i.get("id")): i.get("funnel", []) for i in data.get("issues", [])},
                                ensure_ascii=False, separators=(",", ":"))
                   + f"\nThese {len(notices)} record(s) are all notices of concern that match the request, in priority order. "
                   "shared_by_kind gives, per notice kind, the assumptions and caveats that apply to every "
                   "record of that kind (a record lists its own assumptions only when they differ); each "
                   "record's caveats_for_this_case lists only its additional caveats; rules gives the text "
                   "and citation for each rule_id."
                   + "\nRelevant calculated assessment records (authoritative values; do not recompute):\n"
                   + json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
    })
    usage = usage_summary(data) if wants_usage_view(request_body) else None
    if usage:
        messages.append({
            "role": "system",
            "content": "Finnish usage view of the same results per issue (regrouped per Finnish frequency band "
                       "and per Finnish station; authoritative, do not recompute; keep issues separate). Bands are "
                       "complete; stations are the most affected, up to "
                       f"{USAGE_STATIONS_IN_CONTEXT}, of stationsTotal; say so when listing them:\n"
                       + json.dumps(usage, ensure_ascii=False, separators=(",", ":")),
        })
    if scope:
        if scope.get("wants_trends") and data.get("trends"):
            messages.append({
                "role": "system",
                "content": "Neighbour activity trends and anomaly flags (terrestrial; authoritative). These are "
                           "activity signals about other administrations' notices, not interference findings: "
                           "keep them apart from notices of concern and do not call them risks. Summarise the notable "
                           "ones rather than listing every flag, unless asked for all, and give the reason for those "
                           "you mention:\n"
                           + json.dumps(data["trends"], ensure_ascii=False, separators=(",", ":")),
            })
        frameworks = scope.get("frameworks") or {}
        if scope.get("wants_framework") and frameworks:
            messages.append({
                "role": "system",
                "content": "Regulatory framework per issue (cite provision and page as supplied):\n"
                           + json.dumps(frameworks, ensure_ascii=False, separators=(",", ":")),
            })
    return messages


USAGE_WORDS = ("station", "band", "usage", "frequency range", "frequencies", "most affected", "most exposed",
               "threatened", "allocation")
USAGE_STATIONS_IN_CONTEXT = 30


def wants_usage_view(request_body):
    ref = (request_body.get("context") or {}).get("ref", "")
    query = request_body["messages"][-1]["content"].lower()
    return ref.startswith("station:") or any(word in query for word in USAGE_WORDS)


def usage_summary(data):
    by_issue = data.get("usageByIssue") or {}
    out = {}
    for issue in data.get("issues", []):
        usage = by_issue.get(issue["id"]) or {}
        stations = usage.get("stations", [])
        if not usage.get("bands") and not stations:
            continue
        out[issue.get("label", issue["id"])] = {
            "definitions": usage.get("definitions", {}),
            "bands": usage.get("bands", []),
            "stations": stations[:USAGE_STATIONS_IN_CONTEXT],
            "stationsTotal": len(stations),
        }
    return out or None


MODEL_RETRIES = 2
RETRY_STATUSES = {429, 503}
MAX_RETRY_WAIT_S = 60


def retry_delay_seconds(response):
    header = (response.headers or {}).get("Retry-After") if response is not None else None
    match = None
    if header and str(header).strip().isdigit():
        seconds = int(str(header).strip())
    else:
        match = re.search(r"after (\d+) ?s", response.text if response is not None else "")
        seconds = int(match.group(1)) if match else 10
    return max(1, min(seconds, MAX_RETRY_WAIT_S))


def _stream_completion(messages, api_url, api_key, model):
    for attempt in range(MODEL_RETRIES + 1):
        try:
            response = requests.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}", "x-opencode-session": "traficom-frontend-chat",
                         "Accept": "text/event-stream"},
                json={"model": model, "messages": messages, "stream": True},
                timeout=(15, 180),
                stream=True,
            )
            response.raise_for_status()
            break
        except requests.RequestException as error:
            status = error.response.status_code if isinstance(error, requests.HTTPError) and error.response is not None else None
            if status in RETRY_STATUSES and attempt < MODEL_RETRIES:
                wait = retry_delay_seconds(error.response)
                yield "thinking", f"The model service is busy (HTTP {status}); retrying in {wait} s.\n"
                time.sleep(wait)
                continue
            detail = ""
            if status is not None:
                detail = error.response.text.strip().replace(api_key, "[redacted]")[:300]
                detail = f" HTTP {status}: {detail}"
            raise RuntimeError(f"Model request failed.{detail}") from error
    received = False
    response.encoding = "utf-8"
    try:
        for raw in response.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            payload = raw[len("data:"):].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError as error:
                raise RuntimeError("Model stream contained invalid JSON") from error
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                thinking = delta.get("reasoning_content") or delta.get("reasoning")
                if isinstance(thinking, str) and thinking:
                    received = True
                    yield "thinking", thinking
                text = delta.get("content")
                if isinstance(text, str) and text:
                    received = True
                    yield "text", text
    except requests.RequestException as error:
        raise RuntimeError("Model stream was interrupted.") from error
    finally:
        response.close()
    if not received:
        raise RuntimeError("Model response did not contain a chat answer")


def _chat_events(data, request_body):
    api_url = os.getenv("OPENCODE_API_URL")
    api_key = os.getenv("OPENCODE_API_KEY")
    model = os.getenv("OPENCODE_MODEL", "opencode/big-pickle")
    if not api_url or not api_key:
        yield {"type": "error", "message": "Configure OPENCODE_API_URL and OPENCODE_API_KEY on the backend."}
        return

    scope = route_request(data, request_body)
    data = scoped_data(data, scope)
    notices = _notices_for_request(data, request_body)
    answer = ""
    try:
        for kind, piece in _stream_completion(_model_messages(data, request_body, notices, scope), api_url, api_key, model):
            if kind == "text":
                answer += piece
            yield {"type": kind, "text": piece}
    except RuntimeError as error:
        yield {"type": "error", "message": str(error)}
        return

    mentioned = [n for n in notices if re.search(rf"(?<!\d){re.escape(n['noticeId'])}(?!\d)", answer)]
    notices = mentioned or notices[:1]

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


JOBS = Jobs()


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
            if is_allowed_origin(origin):
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
            if path.startswith("/api/analyses/"):
                job = JOBS.get(path.rsplit("/", 1)[1])
                self._json(200 if job else 404, job or {"error": "Not found"})
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
            parts = urlsplit(self.path)
            path = parts.path
            if path == "/api/uploads":
                try:
                    name = (parse_qs(parts.query).get("name") or [""])[0]
                    length = int(self.headers.get("Content-Length", "0"))
                    self._json(200, receive_upload(self.rfile, length, name))
                except ValueError as error:
                    self._json(400, {"error": str(error)})
                except OSError as error:
                    self._json(503, {"error": f"The file could not be stored: {error}"})
                return
            if path == "/api/analyses":
                try:
                    body = self._read_json()
                    files = body.get("files") if isinstance(body, dict) else None
                    if not isinstance(files, list):
                        raise ValueError("files must be a list of file names")
                    self._json(202, JOBS.start(files))
                except ValueError as error:
                    self._json(400, {"error": str(error)})
                except RuntimeError as error:
                    self._json(409, {"error": str(error)})
                return
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
    load_dotenv(PROJECT_ROOT / "backend" / ".env")
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
