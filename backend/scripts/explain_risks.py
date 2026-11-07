"""Print model-generated explanations for the highest-priority assessment results."""

import argparse
import json
import os
from pathlib import Path
import sys

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPACE_RESULTS = PROJECT_ROOT / "output/ific3074/pfd-calculations/case_pfd_results.jsonl"
DEFAULT_TERRESTRIAL_RESULTS = PROJECT_ROOT / "output/brific3076/terrestrial_ific3076_findings.jsonl"


def read_jsonl(path):
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
    return records


def satellite_notice_summaries(path, limit):
    notices = {}
    for record in read_jsonl(path):
        result = record.get("result", {})
        status = result.get("status")
        if status not in {
            "exceeds_limit",
            "candidate_exceeds_limit",
            "near_limit",
            "candidate_near_limit",
            "unallocated_service_rr_4_4",
        }:
            continue
        notice_id = record.get("space", {}).get("notice_id", record.get("notice_id"))
        if notice_id is None:
            continue
        entry = notices.setdefault(notice_id, {"count": 0, "records": []})
        entry["count"] += 1
        entry["records"].append(record)

    summaries = []
    for notice_id, entry in notices.items():
        worst = min(
            entry["records"],
            key=lambda item: (
                item.get("result", {}).get("worst_margin_db") is None,
                item.get("result", {}).get("worst_margin_db", float("inf")),
            ),
        )
        summaries.append(_satellite_payload(worst, entry["count"]))

    summaries.sort(key=lambda item: (
        item["priority_rank"],
        item["margin_db"] if item["margin_db"] is not None else float("inf"),
    ))
    return summaries[:limit]


def _satellite_payload(record, flagged_case_count):
    result = record.get("result", {})
    criterion_id = result.get("governing_criterion_id")
    evaluation = next(
        (item for item in record.get("evaluations", [])
         if item.get("criterion_id") == criterion_id),
        {},
    )
    station = record.get("finnish_station", {})
    band = station.get("protected_band", {})
    citation = result.get("regulation_citation", {})
    status = result.get("status")
    return {
        "assessment": "satellite PFD",
        "priority_rank": 0 if status in {"exceeds_limit", "candidate_exceeds_limit"} else (
            1 if status in {"near_limit", "candidate_near_limit"} else 2
        ),
        "status": status,
        "notice_id": record.get("space", {}).get("notice_id", record.get("notice_id")),
        "administration": record.get("space", {}).get("administration"),
        "satellite_names": record.get("satellite_names", []),
        "provision": record.get("space", {}).get("provision"),
        "publication_date": record.get("space", {}).get("publication_date"),
        "review_case_count_for_notice": flagged_case_count,
        "station_number": station.get("station_number"),
        "protected_band_mhz": [
            band["frequency_min_hz"] / 1_000_000,
            band["frequency_max_hz"] / 1_000_000,
        ] if band.get("frequency_min_hz") is not None and band.get("frequency_max_hz") is not None else None,
        "frequency_relation": record.get("frequency_relation"),
        "pfd_db": result.get("pfd_db"),
        "limit_db": result.get("limit_db"),
        "reference_bandwidth_hz": result.get("reference_bandwidth_hz"),
        "margin_db": result.get("worst_margin_db"),
        "worst_elevation_deg": result.get("worst_elevation_deg"),
        "criterion_id": criterion_id,
        "criterion_applicability": result.get("governing_applicability"),
        "service_match": evaluation.get("service"),
        "article5_sharing_results": [
            item.get("result") for item in evaluation.get("sharing", {}).get("article5_region1", [])
        ],
        "finland_m4_context": result.get("national_context_m4"),
        "citation": {
            "provision": citation.get("provision"),
            "printed_page": citation.get("printed_page"),
            "document": citation.get("document"),
        },
        "caveats": evaluation.get("caveats", []),
        "assumptions": record.get("assumptions", []),
    }


def terrestrial_summaries(path, limit):
    records = [
        record for record in read_jsonl(path)
        if record.get("result") == "exceeds_threshold"
    ]
    records.sort(key=lambda item: item.get("margin_db", float("-inf")), reverse=True)
    return [
        {
            "assessment": "terrestrial land-mobile field strength",
            "status": record.get("result"),
            "administration": record.get("administration"),
            "assignment_id": record.get("assignment_id"),
            "event": record.get("event"),
            "frequency_mhz": record.get("frequency_mhz"),
            "distance_km": record.get("distance_km"),
            "assessment_location_kind": record.get("assessment_kind"),
            "field_strength_dbuv_m": record.get("field_strength_dbuv_m"),
            "threshold_dbuv_m": record.get("threshold_dbuv_m"),
            "margin_db": record.get("margin_db"),
            "power_dbw": record.get("power_dbw"),
            "power_type": record.get("power_type"),
            "effective_tx_height_m": record.get("effective_tx_height_m"),
            "assessment_coordinates": [
                record.get("assessment_latitude"),
                record.get("assessment_longitude"),
            ],
            "criterion": record.get("criterion"),
            "model": record.get("model"),
            "assumptions": record.get("sources", []),
        }
        for record in records[:limit]
    ]


def explain_with_model(payload, api_url, api_key, model):
    prompt = (
        "Explain this radio-spectrum screening result for a technical reviewer in plain language. "
        "Use only the supplied JSON. State what the measured/calculated quantity and threshold are, "
        "the margin and why this result deserves review. Distinguish a screening exceedance from "
        "proof of harmful interference or a regulatory violation. Include material assumptions and "
        "caveats. Cite only the supplied criterion and page; if absent, say so. Do not recalculate "
        "values, invent propagation effects, or infer real-world harm. Keep the answer under 120 words.\n\n"
        f"Evidence JSON:\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )
    try:
        response = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "x-opencode-session": "traficom-risk-explanations",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=90,
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        response = error.response
        detail = response.text.strip().replace(api_key, "[redacted]")[:500] if response is not None else ""
        if response is not None and response.status_code == 403 and "1010" in detail:
            raise RuntimeError(
                "Model API returned HTTP 403 (Cloudflare error 1010: request blocked). "
                "The endpoint blocked this network request before model authentication; "
                "verify the configured endpoint and network access."
            ) from error
        message = f"Model API returned HTTP {response.status_code if response is not None else 'error'}"
        if detail:
            message += f": {detail}"
        raise RuntimeError(message) from error
    except requests.RequestException as error:
        raise RuntimeError(f"Could not complete the model API request: {error}") from error

    try:
        body = response.json()
    except requests.JSONDecodeError as error:
        raise RuntimeError("Model API returned an invalid JSON response") from error

    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise RuntimeError("Model API response did not contain a chat completion") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3, help="Top cases/notices per assessment (default: 3)")
    parser.add_argument("--space-results", type=Path, default=DEFAULT_SPACE_RESULTS)
    parser.add_argument("--terrestrial-results", type=Path, default=DEFAULT_TERRESTRIAL_RESULTS)
    parser.add_argument("--show-evidence", action="store_true", help="Print the evidence sent to the model")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    load_dotenv(PROJECT_ROOT / ".env")
    api_url = os.getenv("OPENCODE_API_URL")
    api_key = os.getenv("OPENCODE_API_KEY")
    model = os.getenv("OPENCODE_MODEL", "opencode/big-pickle")
    if not api_url or not api_key:
        parser.error("Configure OPENCODE_API_URL and OPENCODE_API_KEY in .env or the environment")

    inputs = []
    for label, path, load in (
        ("SATELLITE", args.space_results, satellite_notice_summaries),
        ("TERRESTRIAL", args.terrestrial_results, terrestrial_summaries),
    ):
        if not path.is_file():
            print(f"{label}: results file not found: {path}", file=sys.stderr)
            continue
        inputs.extend((label, payload) for payload in load(path, args.limit))

    if not inputs:
        parser.error("No assessment results found; run the risk assessments first")

    print(f"AI explanations using configured model: {model}")
    print("Selected result evidence will be sent to that model API for explanation.\n")
    for label, payload in inputs:
        print(f"=== {label}: {payload.get('status')} ===")
        if args.show_evidence:
            print(f"Evidence: {json.dumps(payload, ensure_ascii=False)}")
        print("AI explanation:")
        try:
            explanation = explain_with_model(payload, api_url, api_key, model)
        except RuntimeError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(explanation)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
