from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output"
TARGET = ROOT / "frontend" / "public" / "data" / "assessment.json"
CRITERIA = ROOT / "backend" / "src" / "app" / "reference" / "pfd_criteria.json"

SPACE_CONCERN = ("exceeds_limit", "near_limit", "unallocated_service_rr_4_4")
SPACE_REVIEW = ("missing_input", "parameter_missing", "special_method_required", "candidate_exceeds_limit",
                "candidate_near_limit", "candidate_below_limit")


RESPONSE_RULES = {"9.1/IA": "RR No. 9.3", "9.1": "RR No. 9.3", "9.6": "RR No. 9.52"}
RESPONSE_MONTHS = 4


def add_months(iso_date: str, months: int) -> str:
    year, month, day = (int(x) for x in iso_date[:10].split("-"))
    month += months
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    last = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return f"{year:04d}-{month:02d}-{min(day, last[month - 1]):02d}"


def response_deadline(provision, publication_date) -> dict:
    rule = RESPONSE_RULES.get(str(provision or ""))
    if not rule or not publication_date:
        return {"date": "", "rule": ""}
    return {"date": add_months(str(publication_date), RESPONSE_MONTHS), "rule": rule}


def stations_of(notices: list[dict]) -> int:
    return len({s["id"] for n in notices for s in n.get("stations", []) if s.get("id") != "Border point"})
TERRESTRIAL_CONCERN = ("exceeds_threshold", "near_threshold")
PRIORITY = {"exceeds_limit": 0, "exceeds_threshold": 0, "near_limit": 1, "near_threshold": 1,
            "unallocated_service_rr_4_4": 2}
MAX_STATION_ROWS = 100_000

ADMINISTRATIONS = {
    "AFS": ("ZAF", "South Africa"), "ALB": ("ALB", "Albania"), "ALG": ("DZA", "Algeria"),
    "ARG": ("ARG", "Argentina"), "ARM": ("ARM", "Armenia"), "ARS": ("SAU", "Saudi Arabia"),
    "AUS": ("AUS", "Australia"), "AUT": ("AUT", "Austria"), "AZE": ("AZE", "Azerbaijan"),
    "B": ("BRA", "Brazil"), "BEL": ("BEL", "Belgium"), "BGD": ("BGD", "Bangladesh"),
    "BHR": ("BHR", "Bahrain"), "BIH": ("BIH", "Bosnia and Herzegovina"), "BLR": ("BLR", "Belarus"),
    "BOL": ("BOL", "Bolivia"), "BUL": ("BGR", "Bulgaria"), "CAN": ("CAN", "Canada"),
    "CBG": ("KHM", "Cambodia"), "CHL": ("CHL", "Chile"), "CHN": ("CHN", "China"),
    "CLM": ("COL", "Colombia"), "CYP": ("CYP", "Cyprus"), "CZE": ("CZE", "Czech Republic"),
    "D": ("DEU", "Germany"), "DNK": ("DNK", "Denmark"), "E": ("ESP", "Spain"),
    "EGY": ("EGY", "Egypt"), "EQA": ("ECU", "Ecuador"), "EST": ("EST", "Estonia"),
    "F": ("FRA", "France"), "FIN": ("FIN", "Finland"), "G": ("GBR", "United Kingdom"),
    "GEO": ("GEO", "Georgia"), "GRC": ("GRC", "Greece"), "HNG": ("HUN", "Hungary"),
    "HOL": ("NLD", "Netherlands"), "HRV": ("HRV", "Croatia"), "I": ("ITA", "Italy"),
    "IND": ("IND", "India"), "INS": ("IDN", "Indonesia"), "IRL": ("IRL", "Ireland"),
    "IRN": ("IRN", "Iran"), "ISL": ("ISL", "Iceland"), "ISR": ("ISR", "Israel"),
    "J": ("JPN", "Japan"), "JOR": ("JOR", "Jordan"), "KAZ": ("KAZ", "Kazakhstan"),
    "KEN": ("KEN", "Kenya"), "KGZ": ("KGZ", "Kyrgyzstan"), "KOR": ("KOR", "Korea"),
    "KWT": ("KWT", "Kuwait"), "LAO": ("LAO", "Laos"), "LBN": ("LBN", "Lebanon"),
    "LTU": ("LTU", "Lithuania"), "LUX": ("LUX", "Luxembourg"), "LVA": ("LVA", "Latvia"),
    "MDA": ("MDA", "Moldova"), "MEX": ("MEX", "Mexico"), "MKD": ("MKD", "North Macedonia"),
    "MLA": ("MYS", "Malaysia"), "MLT": ("MLT", "Malta"), "MNG": ("MNG", "Mongolia"),
    "MRC": ("MAR", "Morocco"), "NIG": ("NGA", "Nigeria"), "NOR": ("NOR", "Norway"),
    "NZL": ("NZL", "New Zealand"), "OMA": ("OMN", "Oman"), "PAK": ("PAK", "Pakistan"),
    "PHL": ("PHL", "Philippines"), "PNG": ("PNG", "Papua New Guinea"), "POL": ("POL", "Poland"),
    "POR": ("PRT", "Portugal"), "PRG": ("PRY", "Paraguay"), "PRK": ("PRK", "North Korea"),
    "PRU": ("PER", "Peru"), "QAT": ("QAT", "Qatar"), "ROU": ("ROU", "Romania"),
    "RUS": ("RUS", "Russian Federation"), "S": ("SWE", "Sweden"), "SNG": ("SGP", "Singapore"),
    "SRB": ("SRB", "Serbia"), "SUI": ("CHE", "Switzerland"), "SVK": ("SVK", "Slovakia"),
    "SVN": ("SVN", "Slovenia"), "THA": ("THA", "Thailand"), "TJK": ("TJK", "Tajikistan"),
    "TKM": ("TKM", "Turkmenistan"), "TUN": ("TUN", "Tunisia"), "TUR": ("TUR", "Türkiye"),
    "UAE": ("ARE", "United Arab Emirates"), "UKR": ("UKR", "Ukraine"), "URG": ("URY", "Uruguay"),
    "USA": ("USA", "United States"), "UZB": ("UZB", "Uzbekistan"), "VEN": ("VEN", "Venezuela"),
    "VTN": ("VNM", "Viet Nam"),
}

COUNT_DEFINITIONS = {
    "casesOfConcern": "Cases of this notice with a status of concern (exceeds, near the limit or unallocated "
                      "service). One case is one Finnish station and protected band against one notice.",
    "stationsAffected": "Distinct Finnish stations (or assessment points) among the cases of concern.",
    "priority": "Rank across all notices, computed in code: status (exceeds, then near, then unallocated "
                "service), then worst margin (most negative first), then stations affected.",
}
RR_4_4_TEXT = "The service is not allocated in Region 1 for this band and operates under RR No. 4.4."

PROVISIONS = {"9.1/IA": "9.1 advance publication", "9.1": "9.1 advance publication", "IA": "9.1 advance publication", "9.6": "9.6 coordination",
              "11.2": "11.2 notification", "RS49": "Resolution 49"}


def clean(text: str) -> str:
    text = text.replace("—", ", ").replace("·", ", ")
    text = re.sub(r"(\d)\s?[-–]\s?(\d[\d ]*(?:\.\d+)?\s?[kMG]Hz)", r"\1 to \2", text)
    text = re.sub(r"(\d°?) - (\w)", "\\1 \u2212 \\2", text)
    text = re.sub(r"(^|[\s(])-(\d)", "\\1\u2212\\2", text)
    text = text.replace(" - ", ", ").replace(" | ", ", ").replace(" / ", ", ")
    return text


def safe_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        d = datetime.fromisoformat(value[:10])
    except ValueError:
        return value
    return f"{d.day} {d.strftime('%B %Y')}"


def hz(value: float) -> str:
    if value >= 1e9:
        return f"{value / 1e9:.4g} GHz"
    if value >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    return f"{value / 1e3:.4g} kHz"


def band(pb: dict) -> str:
    lo, hi = pb.get("frequency_min_hz"), pb.get("frequency_max_hz")
    if lo is None or hi is None:
        return ""
    return f"{hz(lo)} to {hz(hi)}"


UNKNOWN_CODES: set[str] = set()


def admin(code: str) -> str:
    return ADMINISTRATIONS.get(code, (code, code))[1]


def iso(code: str) -> str:
    if code in ADMINISTRATIONS:
        return ADMINISTRATIONS[code][0]
    UNKNOWN_CODES.add(code)
    return code


def criterion_text(crit: dict | None) -> str:
    if not crit:
        return ""
    services = ", ".join(crit.get("services", []))
    bands = ", ".join(b.get("label", "") for b in crit.get("bands", []))
    orbit = {"gso": "geostationary", "non_gso": "non geostationary", "any": "any orbit"}.get(crit.get("orbit"), crit.get("orbit", ""))
    segs = []
    for s in crit.get("segments", []):
        formula = str(s.get("source_text", s.get("formula"))).replace(" - ", " − ")
        segs.append(f"{formula} dB(W/m²) for {s['elev_min_deg']}° to {s['elev_max_deg']}° elevation")
    ref = hz(crit["reference_bandwidth_hz"]) if crit.get("reference_bandwidth_hz") else ""
    parts = [f"{services} in {bands}, {orbit}"]
    if segs:
        parts.append("Limit " + ", ".join(segs) + (f" in {ref}" if ref else ""))
    return clean(". ".join(parts) + ".")


def m4_context(case: dict) -> tuple[str, str]:
    governing = case["result"].get("governing_criterion_id")
    evaluations = case.get("evaluations", [])
    ordered = [e for e in evaluations if e.get("criterion_id") == governing] + evaluations
    for e in ordered:
        m4 = (e.get("sharing") or {}).get("m4_finland") or {}
        bands = m4.get("bands") or []
        if bands:
            label = re.sub(r"\s+-\s+", " to ", bands[0].get("m4_band", "")).strip()
            return clean(label), m4.get("partner_in_finland", "")
    return "", ""


def usage_views(notices: list[dict]) -> dict:
    bands: dict[str, dict] = {}
    stations: dict[str, dict] = {}
    for n in notices:
        context = n.get("nationalContext") or {}
        for s in n.get("stations", []):
            label = s.get("finnishBand") or next(iter(context.get("m4Bands") or []), "") or s.get("band") or ""
            national_use = s.get("nationalUse") or context.get("mobileInFinland", "")
            b = bands.setdefault(label, {"band": label, "kind": n["kind"], "nationalUse": national_use,
                                         "stations": set(), "notices": set(), "cases": 0, "worstMarginDb": None,
                                         "worstNoticeKey": "", "worstNoticeName": "", "worstRuleId": "",
                                         "statusCounts": {}})
            if s["id"] != "Border point":
                b["stations"].add(s["id"])
            b["notices"].add(n["key"])
            b["cases"] += 1
            b["statusCounts"][s["status"]] = b["statusCounts"].get(s["status"], 0) + 1
            if s.get("marginDb") is not None and (b["worstMarginDb"] is None or s["marginDb"] < b["worstMarginDb"]):
                b.update(worstMarginDb=s["marginDb"], worstNoticeKey=n["key"], worstNoticeName=n["name"],
                         worstRuleId=s.get("ruleId") or n.get("rule", {}).get("id", ""))
            if s["id"] == "Border point":
                continue
            st = stations.setdefault(s["id"], {"id": s["id"], "latitude": s["latitude"], "longitude": s["longitude"],
                                               "bands": set(), "notices": set(), "cases": 0, "worstMarginDb": None,
                                               "worstNoticeKey": "", "worstNoticeName": ""})
            st["bands"].add(label)
            st["notices"].add(n["key"])
            st["cases"] += 1
            if s.get("marginDb") is not None and (st["worstMarginDb"] is None or s["marginDb"] < st["worstMarginDb"]):
                st.update(worstMarginDb=s["marginDb"], worstNoticeKey=n["key"], worstNoticeName=n["name"])

    def order(item):
        return (item["worstMarginDb"] if item["worstMarginDb"] is not None else 0, -len(item["notices"]))

    band_rows = []
    for b in sorted(bands.values(), key=order):
        band_rows.append({**b, "stations": len(b["stations"]), "notices": len(b["notices"])})
    station_rows = []
    for st in sorted(stations.values(), key=order):
        station_rows.append({**st, "bands": sorted(st["bands"]), "notices": len(st["notices"])})
    return {
        "definitions": {
            "band": "Finland's M4 frequency allocation band of the protected station (space) or of the "
                    "foreign assignment's frequency (terrestrial).",
            "nationalUse": "Category of Finland's fixed (space) or mobile (terrestrial) allocation in that M4 band "
                           "(primary, secondary, not_listed).",
            "cases": "Cases of concern: one notice against one Finnish station and protected band.",
            "worstMarginDb": "Most negative margin among those cases (negative = above the limit).",
            "worstRuleId": "Rule (Table 21-4 row or terrestrial criterion) of that worst case.",
        },
        "bands": band_rows,
        "stations": station_rows,
    }


def case_caveats(case: dict) -> list[str]:
    result = case["result"]
    governing = result.get("governing_criterion_id")
    found = []
    for e in case.get("evaluations", []):
        if not governing or e.get("criterion_id") != governing:
            continue
        for cv in e.get("caveats") or []:
            t = caveat_text(cv)
            if t and t not in found:
                found.append(t)
    if result["status"] == "unallocated_service_rr_4_4" and RR_4_4_TEXT not in found:
        found.append(RR_4_4_TEXT)
    return found


def caveat_text(c) -> str:
    if isinstance(c, dict):
        c = c.get("text") or c.get("message") or json.dumps(c)
    c = str(c)
    if ": " in c and re.match(r"^[a-z0-9_]+: ", c):
        c = c.split(": ", 1)[1]
    return clean(c[0].upper() + c[1:]) if c else c


def space_issue(folder: Path, criteria: dict) -> tuple[dict, list[dict]]:
    pfd = folder / "pfd-calculations"
    summary = json.loads((pfd / "pfd_summary.json").read_text(encoding="utf8"))
    issue_no = re.sub(r"\D", "", folder.name)
    issue_id = folder.name
    by_notice: dict[int, list[dict]] = defaultdict(list)
    calculated_notices, exceeding_notices, review_notices = set(), set(), set()
    published = Counter()
    with (pfd / "case_pfd_results.jsonl").open(encoding="utf8") as fh:
        for line in fh:
            r = json.loads(line)
            if str(r["space"].get("notice_publication_issue")) == issue_no and r["space"].get("publication_date"):
                published[str(r["space"]["publication_date"])[:10]] += 1
            calculated_notices.add(r["notice_id"])
            if r["result"]["status"] in SPACE_REVIEW:
                review_notices.add(r["notice_id"])
            if r["result"]["status"] == "exceeds_limit":
                exceeding_notices.add(r["notice_id"])
            if r["result"]["status"] in SPACE_CONCERN:
                by_notice[r["notice_id"]].append(r)

    standard_caveats = ["A screening value is a reason for expert review, not proof of harmful interference."]
    status = summary.get("criteria_transcription_status", "")
    transcription_note = ""
    if status.startswith("unverified"):
        standard_caveats.append("The Table 21-4 transcription is unverified and should be checked against the printed Radio Regulations.")
    elif status == "ai_transcription_cross_checked":
        transcription_note = ("Table 21-4 limits were transcribed with AI assistance and cross-checked row by row against "
                              "the printed Radio Regulations, pages 287 to 291; expert verification is pending.")

    notices = []
    for notice_id, cases in by_notice.items():
        cases.sort(key=lambda c: (PRIORITY[c["result"]["status"]], c["result"].get("worst_margin_db") or 0))
        worst = cases[0]
        res, sp = worst["result"], worst["space"]
        cit = res.get("regulation_citation") or {}
        own = case_caveats(worst)
        caveats = list(standard_caveats) + [t for t in own if t not in standard_caveats]
        other_counts: dict[str, int] = {}
        for c in cases[1:]:
            for t in case_caveats(c):
                if t not in own:
                    other_counts[t] = other_counts.get(t, 0) + 1
        other_case_caveats = [{"text": t, "cases": n} for t, n in other_counts.items()]
        if worst["result"].get("rr_4_4_unallocated_rows") and worst["result"]["status"] != "unallocated_service_rr_4_4":
            other_case_caveats.append({
                "text": "Another Table 21-4 row considered for the worst case has a satellite service that is not "
                        "allocated in Region 1 (RR No. 4.4); this does not apply to the headline value.",
                "cases": 1,
            })

        stations = []
        for c in cases[:MAX_STATION_ROWS]:
            fs, cr = c["finnish_station"], c["result"]
            m4_band, national_use = m4_context(c)
            stations.append({
                "id": fs["station_number"],
                "latitude": fs["latitude"],
                "longitude": fs["longitude"],
                "band": band(fs.get("protected_band") or {}),
                "finnishBand": m4_band,
                "nationalUse": national_use,
                "ruleId": cr.get("governing_criterion_id") or "",
                "status": cr["status"],
                "value": cr.get("pfd_db"),
                "limit": cr.get("limit_db"),
                "marginDb": cr.get("worst_margin_db"),
            })

        ev = worst["evidence"]
        datasets = ev["source_datasets"]
        space_ds = datasets["space"]
        wb = datasets.get("finnish_workbook", {})
        rows = []
        tables = {"orbit_context": "geo", "frequency": "freq", "group": "grp", "emission": "emiss", "beam": "s_beam"}
        for key, entries in ev.get("source_rows", {}).items():
            if key == "finnish_station":
                continue
            entries = entries if isinstance(entries, list) else [entries]
            nums = sorted({e["source_row"] if isinstance(e, dict) else e for e in entries
                           if isinstance(e, int) or (isinstance(e, dict) and "source_row" in e)})
            if not nums:
                continue
            first = entries[0]
            table = first.get("table") if isinstance(first, dict) else None
            rows.append({"dataset": Path(space_ds["file"]).name, "table": table or tables.get(key, key),
                         "rows": rows_text(nums), "sha256": space_ds["sha256"][:12]})
        station_rows = sorted({c["finnish_station"]["source_row"] for c in cases})
        rows.append({"dataset": Path(wb.get("file", "Finnish workbook")).name, "table": "Frequencies of interest",
                     "rows": rows_text(station_rows), "sha256": wb.get("sha256", "")[:12]})

        affected = len({c["finnish_station"]["station_number"] for c in cases})
        notices.append({
            "key": f"{issue_id}:{notice_id}",
            "issueId": issue_id,
            "kind": "Space",
            "noticeId": str(notice_id),
            "administration": iso(sp["administration"]),
            "ituCode": sp["administration"],
            "administrationName": admin(sp["administration"]),
            "name": clean(", ".join(worst.get("satellite_names") or [f"Notice {notice_id}"])),
            "provision": PROVISIONS.get(sp.get("provision"), sp.get("provision") or ""),
            "publicationDate": safe_date(sp.get("publication_date")),
            "responseDeadline": response_deadline(sp.get("provision"), sp.get("publication_date")),
            "status": res["status"],
            "worstMarginDb": res.get("worst_margin_db"),
            "measure": "PFD",
            "unit": "dB(W/m²)",
            "value": res.get("pfd_db"),
            "limit": res.get("limit_db"),
            "referenceBandwidth": hz(res["reference_bandwidth_hz"]) if res.get("reference_bandwidth_hz") else "",
            "elevationDeg": res.get("worst_elevation_deg"),
            "band": band(worst["finnish_station"].get("protected_band") or {}),
            "rule": {"id": res.get("governing_criterion_id") or "",
                     "text": criterion_text(criteria.get(res.get("governing_criterion_id")))},
            "citation": {"document": clean(cit.get("document", "")), "provision": clean(cit.get("provision", "")),
                         "printedPage": cit.get("printed_page"), "pdfPage": cit.get("pdf_page"),
                         "url": cit.get("source_url")},
            "assumptions": [clean(a) for a in worst.get("assumptions", [])] + ([transcription_note] if transcription_note else []),
            "caveats": caveats,
            "otherCaseCaveats": other_case_caveats,
            "worstCaseId": worst.get("case_id"),
            "stationsAffected": affected,
            "casesOfConcern": len(cases),
            "stations": stations,
            "sourceRows": rows,
        })

    issue = {
        "id": issue_id,
        "label": f"IFIC {issue_no}",
        "kind": "Space",
        "published": published.most_common(1)[0][0] if published else "",
        "counts": summary["counts"],
        "noticesOfConcern": len(notices),
        "highlights": [
            {"label": "Notices above PFD limit", "value": sum(n["status"] == "exceeds_limit" for n in notices)},
            {"label": "Notices near PFD limit", "value": sum(n["status"] == "near_limit" for n in notices)},
            {"label": "Notices without allocation",
             "value": sum(n["status"] == "unallocated_service_rr_4_4" for n in notices)},
            {"label": "Finnish stations affected", "value": stations_of(notices)},
            {"label": "Administrations to contact", "value": len({n["administration"] for n in notices})},
            {"label": "Notices for manual review", "value": len(review_notices - {
                int(n["noticeId"]) for n in notices if str(n["noticeId"]).isdigit()})},
        ],
        "funnel": space_funnel(folder, len(calculated_notices), len(notices), len(exceeding_notices)),
        "runId": summary["run"]["run_id"][:12],
    }
    return issue, notices


def space_funnel(folder: Path, calculated: int, of_concern: int, exceeding: int) -> list[dict]:
    stages = []
    manifest = folder / "prepared" / "manifest.json"
    if manifest.exists():
        datasets = json.loads(manifest.read_text(encoding="utf8")).get("datasets", [])
        evaluated = next((d for d in datasets if Path(d.get("file", "")).name.lower() == f"{folder.name.lower()}.mdb"), None)
        notices = ((evaluated or {}).get("extraction", {}).get("tables", {}).get("notice", {}) or {}).get("records")
        if notices is not None:
            stages.append({"stage": "Notices published in the IFIC", "count": notices})
    rollups = folder / "frequency-cases" / "notice_rollups.csv"
    if rollups.exists():
        with rollups.open(encoding="utf8", newline="") as fh:
            matched = {row["notice_id"] for row in csv.DictReader(fh) if row.get("space_dataset_kind") == "space_ific_evaluation"}
        stages.append({"stage": "Overlapping or adjacent to a Finnish protected frequency", "count": len(matched)})
    stages += [
        {"stage": "PFD calculated", "count": calculated},
        {"stage": "Notices of concern (exceeds, near the limit or unallocated service)", "count": of_concern},
        {"stage": "With at least one case exceeding the limit", "count": exceeding},
    ]
    return stages


def rows_text(nums: list[int], limit: int = 12) -> str:
    shown = ", ".join(str(n) for n in nums[:limit])
    return shown + (f" and {len(nums) - limit} more" if len(nums) > limit else "")


def terrestrial_published(folder: Path, issue_no: str) -> str:
    for path in sorted(folder.glob("prepared/**/pub_current_circ.jsonl")):
        for line in path.open(encoding="utf8"):
            raw = json.loads(line)["raw"]
            if str(raw.get("circ_no")) == issue_no and raw.get("d_pub"):
                return str(raw["d_pub"])[:10]
    return ""


def terrestrial_issue(folder: Path) -> tuple[dict, list[dict], dict | None]:
    summary = json.loads((folder / "terrestrial_summary.json").read_text(encoding="utf8"))
    issue_no = str(summary.get("current_issue") or re.sub(r"\D", "", folder.name))
    issue_id = folder.name
    findings_file = next(folder.glob("terrestrial_*_findings.jsonl"))
    findings = [json.loads(l) for l in findings_file.open(encoding="utf8")]
    crit = summary.get("criterion", {})
    geometry = summary.get("assessment_geometry", {})

    caveats = [
        "A threshold exceedance is a reason for expert review, not proof of harmful interference.",
        "Land-border paths use the P.1546 Land curve and territorial-sea outer-limit paths use the Cold-sea curve; protected-station paths retain the larger Land/Cold prediction when path composition is unknown.",
        "Every co-frequency Finnish station in the supplied workbook is assessed; the station count is not limited to the nearest match.",
        "The nearest point on every official boundary section is calculated, and the section with the highest field strength governs.",
    ]
    extension = clean(crit["challenge_extension"]) if crit.get("challenge_extension") else ""

    notices = []
    for f in findings:
        if f["result"] not in TERRESTRIAL_CONCERN:
            continue
        sn = f.get("source_notice") or {}
        stations = []
        for a in f.get("assessments", []):
            if "field_strength_dbuv_m" not in a:
                continue
            m = a["margin_db"]
            stations.append({
                "id": a.get("station_number") or "Border point",
                "latitude": a["latitude"],
                "longitude": a["longitude"],
                "band": f"{f['frequency_mhz']:g} MHz",
                "status": "exceeds_threshold" if m > 0 else ("near_threshold" if m > -3 else "below_threshold"),
                "value": a["field_strength_dbuv_m"],
                "limit": a["threshold_dbuv_m"],
                "marginDb": -m,
                "distanceKm": a.get("distance_km"),
            })
        affected = len({s["id"] for s in stations if s["id"] != "Border point" and s["status"] != "below_threshold"})
        rows = [{"dataset": f"brific{issue_no}.mdb", "table": "notice", "rows": str(f["source_row"]), "sha256": f["dataset_id"][:12]}]
        if f.get("geography_source_row") is not None:
            rows.append({"dataset": f"brific{issue_no}.mdb", "table": "geography", "rows": str(f["geography_source_row"]), "sha256": f["dataset_id"][:12]})
        if f.get("antenna_source_row") is not None:
            rows.append({"dataset": f"brific{issue_no}.mdb", "table": "antenna", "rows": str(f["antenna_source_row"]), "sha256": f["dataset_id"][:12]})
        model = f.get("model", {})
        notices.append({
            "key": f"{issue_id}:{f['assignment_id']}",
            "issueId": issue_id,
            "kind": "Terrestrial",
            "noticeId": str(f["assignment_id"]),
            "administration": iso(f["administration"]),
            "ituCode": f["administration"],
            "administrationName": admin(f["administration"]),
            "name": f"{sn.get('stn_cls') or 'Station'} {f['frequency_mhz']:g} MHz",
            "provision": f"{(f.get('event') or '').capitalize()} assignment",
            "publicationDate": "",
            "status": f["result"],
            "worstMarginDb": -f["margin_db"],
            "measure": "Field strength",
            "unit": "dB(µV/m)",
            "value": f["field_strength_dbuv_m"],
            "limit": f["threshold_dbuv_m"],
            "referenceBandwidth": hz(crit.get("conditions", {}).get("reference_bandwidth_hz", 0)) if crit.get("conditions", {}).get("reference_bandwidth_hz") else "",
            "elevationDeg": None,
            "distanceKm": f.get("distance_km"),
            "band": f"{f['frequency_mhz']:g} MHz",
            "rule": {"id": clean(crit.get("title", "")),
                     "text": clean(f"Field strength threshold of {f['threshold_dbuv_m']:g} dB(µV/m) at the Finnish border, "
                                   f"{crit.get('conditions', {}).get('time_percentage', '')}% time, "
                                   f"{crit.get('conditions', {}).get('location_percentage', '')}% locations, "
                                   f"receiver height {crit.get('conditions', {}).get('receiver_height_m', '')} m. "
                                   f"Propagation by {model.get('name', 'ITU-R P.1546')}.")},
            "citation": {"document": clean(crit.get("title", "")), "provision": clean(f"Edition {crit.get('edition', '')}"),
                         "printedPage": None, "pdfPage": None, "url": crit.get("url")},
            "assumptions": [clean(a) for a in summary.get("assumptions", [])],
            "caveats": caveats + ([extension] if extension and float(f["frequency_mhz"]) > 470 else []),
            "otherCaseCaveats": [],
            "worstCaseId": str(f["assignment_id"]),
            "nationalContext": {
                "mobileInFinland": (f.get("national_context_m4") or {}).get("mobile_in_finland", ""),
                "m4Bands": [clean(re.sub(r"\s+-\s+", " to ", b.get("band", "")))
                            for b in (f.get("national_context_m4") or {}).get("m4_bands", [])],
            },
            "stationsAffected": affected,
            "casesOfConcern": 1,
            "stations": stations,
            "sourceRows": rows,
        })

    counts = dict(summary.get("counts", {}))
    issue = {
        "id": issue_id,
        "label": f"BR IFIC {issue_no}",
        "kind": "Terrestrial",
        "published": terrestrial_published(folder, issue_no),
        "counts": counts,
        "noticesOfConcern": len(notices),
        "highlights": [
            {"label": "Over field threshold", "value": counts.get("exceeds_threshold", 0)},
            {"label": "Near field threshold", "value": counts.get("near_threshold", 0)},
            {"label": "Finnish stations exposed", "value": summary.get("exposed_protected_station_count", 0)},
            {"label": "Administrations to contact", "value": len({n["administration"] for n in notices})},
            {"label": "Transmitters screened", "value": summary.get("screened_event_count", 0)},
        ],
        "funnel": [
            {"stage": "New, modified or withdrawn foreign land-mobile transmitters screened",
             "count": summary.get("screened_event_count", 0)},
            {"stage": "Within the P.1546 1000 km range, field strength calculated", "count": summary.get("finding_count", 0)},
            {"stage": "Notices of concern (exceeds or near the threshold)", "count": len(notices)},
        ],
        "runId": str(summary.get("run_id", ""))[:12],
        "regulatoryFramework": [
            {"level": item.get("level", ""), "provision": clean(item.get("provision", "")),
             "role": clean(item.get("role", "")), "printedPage": item.get("printed_page"),
             "pdfPage": item.get("pdf_page"), "url": item.get("url"), "file": item.get("file")}
            for item in summary.get("regulatory_framework", [])
        ],
    }
    trends = None
    tf = folder / "terrestrial_trends.json"
    if tf.exists():
        t = json.loads(tf.read_text(encoding="utf8"))
        trends = {
            "issueId": issue_id,
            "previous": f"BR IFIC {summary['previous_issue']}" if summary.get("previous_issue") else "",
            "current": f"BR IFIC {issue_no}",
            "anomalies": [
                {"type": a.get("type", ""), "dimension": a.get("dimension", ""), "subject": clean(str(a.get("subject", ""))),
                 "reason": clean(a.get("reason", "")), "evidence": a.get("evidence", {})}
                for a in t.get("anomalies", [])
            ],
            "neighbourActivity": neighbour_activity(t.get("anomalies", []), findings, notices),
            "anomalyRules": {k: clean(v) for k, v in t.get("anomaly_rules", {}).items()},
            "administrations": [
                {"label": iso(a["administration"]), "previous": a["previous"], "current": a["current"]}
                for a in t.get("administration_activity", [])
            ],
            "bands": [
                {"label": clean(b["band"]), "previous": b["previous"], "current": b["current"]}
                for b in t.get("band_activity", [])
            ],
        }
    return issue, notices, trends


OUTLIER_FLAG = {"height_m": ("Antenna height", "m"), "erp_dbw": ("Transmit power", "dBW"),
                "bandwidth_khz": ("Bandwidth", "kHz")}
BOUNDARY_KINDS = {"land_border", "territorial_sea_outer_limit"}


def neighbour_activity(anomalies, findings, notices):
    concern = {n["noticeId"]: n for n in notices}
    pages = {n["administration"] for n in notices}
    neighbours = {a["administration"] for a in anomalies if a.get("type") == "filing_summary"}
    flags, notes, withdrawn = {}, [], {}
    for a in anomalies:
        ev = a.get("evidence", {})
        if a.get("type") == "new_activity_near_border":
            for item in ev.get("assignments", []):
                flags.setdefault(item["assignment_id"], []).append("New near the border")
        elif a.get("type") == "parameter_outlier":
            word, unit = OUTLIER_FLAG.get(ev.get("metric"), ("Value", ""))
            flags.setdefault(ev.get("assignment_id"), []).append(
                clean(f"{word} {ev.get('value'):g} {unit}, typical {ev.get('band_median'):g} {unit}"))
        elif a.get("type") == "new_station_class":
            notes.append(clean(f"{admin(a['administration'])} filed {ev.get('current', 0)} {ev.get('station_class', '')} "
                               "notices, a station class it did not use in the previous issue."))
        elif a.get("type") == "filing_summary":
            withdrawn[a["administration"]] = ev.get("withdrawn", 0)
    rows = []
    for f in findings:
        code = f.get("administration")
        if code not in neighbours:
            continue
        distances = [x["distance_km"] for x in f.get("assessments", [])
                     if x.get("kind") in BOUNDARY_KINDS and x.get("distance_km") is not None]
        item = str(f["assignment_id"])
        notice = concern.get(item)
        shown = iso(code)
        rows.append({
            "administration": {"text": admin(code), "ref": f"administration:{shown}" if shown in pages else None},
            "assignment": {"text": notice["name"] if notice else f"FB {float(f['frequency_mhz']):g} MHz",
                           "ref": f"notice:{notice['key']}" if notice else None},
            "frequencyMhz": f"{float(f['frequency_mhz']):g}" if f.get("frequency_mhz") is not None else "",
            "distanceKm": round(min(distances), 1) if distances else None,
            "marginDb": -round(f["margin_db"], 2) if f.get("margin_db") is not None else None,
            "event": f.get("event", ""),
            "status": f.get("result", ""),
            "flags": flags.get(item, []),
        })
    for code, n in sorted(withdrawn.items()):
        if n:
            notes.append(f"{admin(code)} withdrew {n} base station{'s' if n != 1 else ''} in this issue.")
    return {"rows": rows, "notes": notes}


def rounded(value):
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


def main() -> None:
    criteria = {c["criterion_id"]: c for c in json.loads(CRITERIA.read_text(encoding="utf8"))["criteria"]}
    issues, notices, trends = [], [], []
    for folder in sorted(OUTPUT.glob("ific*")):
        if (folder / "pfd-calculations" / "case_pfd_results.jsonl").exists():
            i, n = space_issue(folder, criteria)
            issues.append(i)
            notices += n
    for folder in sorted(OUTPUT.glob("brific*")):
        if (folder / "terrestrial_summary.json").exists():
            i, n, t = terrestrial_issue(folder)
            issues.append(i)
            notices += n
            if t:
                trends.append(t)

    notices.sort(key=lambda n: (PRIORITY[n["status"]], n["worstMarginDb"] if n["worstMarginDb"] is not None else 0,
                                -n["stationsAffected"]))
    for rank, n in enumerate(notices, 1):
        n["priority"] = rank

    data = {
        "generated": safe_date(datetime.now().isoformat()),
        "countDefinitions": COUNT_DEFINITIONS,
        "issues": issues,
        "notices": notices,
        "usageByIssue": {i["id"]: usage_views([n for n in notices if n["issueId"] == i["id"]]) for i in issues},
        "trends": trends,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(rounded(data), ensure_ascii=False), encoding="utf8")
    print(f"Wrote {TARGET.relative_to(ROOT)}: {len(issues)} issues, {len(notices)} notices of concern")
    if UNKNOWN_CODES:
        print("Add these ITU administration codes to ADMINISTRATIONS:", ", ".join(sorted(UNKNOWN_CODES)))


if __name__ == "__main__":
    main()
