"""Export calculation results from output/ into one JSON file for the frontend.

Usage (from the project folder):
    python backend/scripts/export_frontend_data.py

Reads every output/ific*/pfd-calculations and output/brific* folder that exists and
writes frontend/public/data/assessment.json. Numbers, statuses and citations are copied
from the records; the script only groups and orders them.

Margin convention in the export: negative = above the limit (same as the space records).
Terrestrial margins are therefore sign-flipped.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output"
TARGET = ROOT / "frontend" / "public" / "data" / "assessment.json"
CRITERIA = ROOT / "backend" / "src" / "app" / "reference" / "pfd_criteria.json"

SPACE_CONCERN = ("exceeds_limit", "near_limit", "unallocated_service_rr_4_4")
TERRESTRIAL_CONCERN = ("exceeds_threshold", "near_threshold")
PRIORITY = {"exceeds_limit": 0, "exceeds_threshold": 0, "near_limit": 1, "near_threshold": 1,
            "unallocated_service_rr_4_4": 2}
MAX_STATION_ROWS = 100_000  # effectively all cases

ADMINISTRATIONS = {
    "ARS": "Saudi Arabia", "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium", "BHR": "Bahrain",
    "BLR": "Belarus", "CAN": "Canada", "CHN": "China", "CYP": "Cyprus", "D": "Germany", "DNK": "Denmark",
    "E": "Spain", "EGY": "Egypt", "EST": "Estonia", "F": "France", "FIN": "Finland", "G": "United Kingdom",
    "GRC": "Greece", "HOL": "Netherlands", "I": "Italy", "IND": "India", "INS": "Indonesia", "IRN": "Iran",
    "ISR": "Israel", "J": "Japan", "KAZ": "Kazakhstan", "KOR": "Korea", "LTU": "Lithuania", "LUX": "Luxembourg",
    "LVA": "Latvia", "MLA": "Malaysia", "NOR": "Norway", "PAK": "Pakistan", "PNG": "Papua New Guinea", "PHL": "Philippines", "ARG": "Argentina", "BRA": "Brazil", "MEX": "Mexico", "NZL": "New Zealand", "MNG": "Mongolia", "AZE": "Azerbaijan", "ARM": "Armenia", "GEO": "Georgia", "BUL": "Bulgaria", "ROU": "Romania", "HNG": "Hungary", "CZE": "Czech Republic", "SVK": "Slovakia", "POR": "Portugal", "IRL": "Ireland", "NIG": "Nigeria", "AFS": "South Africa", "KEN": "Kenya", "ALG": "Algeria", "MRC": "Morocco", "TUN": "Tunisia", "OMA": "Oman", "KWT": "Kuwait", "JOR": "Jordan", "LBN": "Lebanon", "BGD": "Bangladesh", "LAO": "Laos", "CBG": "Cambodia", "PRK": "North Korea", "TKM": "Turkmenistan", "KGZ": "Kyrgyzstan", "TJK": "Tajikistan", "MDA": "Moldova", "SRB": "Serbia", "HRV": "Croatia", "BIH": "Bosnia and Herzegovina", "MKD": "North Macedonia", "ALB": "Albania", "MLT": "Malta", "ISL": "Iceland", "PRG": "Paraguay", "URG": "Uruguay", "CHL": "Chile", "CLM": "Colombia", "PRU": "Peru", "VEN": "Venezuela", "B": "Brazil", "BOL": "Bolivia", "EQA": "Ecuador",
    "POL": "Poland", "QAT": "Qatar", "RUS": "Russian Federation", "S": "Sweden", "SNG": "Singapore",
    "SUI": "Switzerland", "SVN": "Slovenia", "THA": "Thailand", "TUR": "Türkiye", "UAE": "United Arab Emirates",
    "UKR": "Ukraine", "USA": "United States", "UZB": "Uzbekistan", "VTN": "Viet Nam",
}

PROVISIONS = {"9.1/IA": "9.1 advance publication", "9.1": "9.1 advance publication", "IA": "9.1 advance publication", "9.6": "9.6 coordination",
              "11.2": "11.2 notification", "RS49": "Resolution 49"}


def clean(text: str) -> str:
    """Remove separator characters the UI rules forbid."""
    text = text.replace("—", ", ").replace("·", ", ")
    text = re.sub(r"(\d)\s?[-–]\s?(\d[\d ]*(?:\.\d+)?\s?[kMG]Hz)", r"\1 to \2", text)  # band ranges
    text = re.sub(r"(\d°?) - (\w)", "\\1 \u2212 \\2", text)  # arithmetic minus
    text = re.sub(r"(^|[\s(])-(\d)", "\\1\u2212\\2", text)  # negative numbers
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


def admin(code: str) -> str:
    return ADMINISTRATIONS.get(code, code)


def criterion_text(crit: dict | None) -> str:
    if not crit:
        return ""
    services = ", ".join(crit.get("services", []))
    bands = ", ".join(b.get("label", "") for b in crit.get("bands", []))
    orbit = {"gso": "geostationary", "non_gso": "non geostationary", "any": "any orbit"}.get(crit.get("orbit"), crit.get("orbit", ""))
    segs = []
    for s in crit.get("segments", []):
        formula = str(s.get("source_text", s.get("formula"))).replace(" - ", " − ")  # math, not a separator
        segs.append(f"{formula} dB(W/m²) for {s['elev_min_deg']}° to {s['elev_max_deg']}° elevation")
    ref = hz(crit["reference_bandwidth_hz"]) if crit.get("reference_bandwidth_hz") else ""
    parts = [f"{services} in {bands}, {orbit}"]
    if segs:
        parts.append("Limit " + ", ".join(segs) + (f" in {ref}" if ref else ""))
    return clean(". ".join(parts) + ".")


def caveat_text(c) -> str:
    if isinstance(c, dict):
        c = c.get("text") or c.get("message") or json.dumps(c)
    c = str(c)
    if ": " in c and re.match(r"^[a-z0-9_]+: ", c):
        c = c.split(": ", 1)[1]
    return clean(c[0].upper() + c[1:]) if c else c


# ------------------------------------------------------------------ space


def space_issue(folder: Path, criteria: dict) -> tuple[dict, list[dict]]:
    pfd = folder / "pfd-calculations"
    summary = json.loads((pfd / "pfd_summary.json").read_text(encoding="utf8"))
    issue_no = re.sub(r"\D", "", folder.name)
    issue_id = folder.name
    by_notice: dict[int, list[dict]] = defaultdict(list)
    with (pfd / "case_pfd_results.jsonl").open(encoding="utf8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["result"]["status"] in SPACE_CONCERN:
                by_notice[r["notice_id"]].append(r)

    standard_caveats = ["A screening value is a reason for expert review, not proof of harmful interference."]
    if summary.get("criteria_transcription_status", "").startswith("unverified"):
        standard_caveats.append("The Table 21-4 transcription is unverified and should be checked against the printed Radio Regulations.")

    notices = []
    for notice_id, cases in by_notice.items():
        cases.sort(key=lambda c: (PRIORITY[c["result"]["status"]], c["result"].get("worst_margin_db") or 0))
        worst = cases[0]
        res, sp = worst["result"], worst["space"]
        cit = res.get("regulation_citation") or {}
        caveats = list(standard_caveats)
        for c in cases:
            for e in c.get("evaluations", []):
                for cv in e.get("caveats") or []:
                    t = caveat_text(cv)
                    if t and t not in caveats:
                        caveats.append(t)
            if c["result"]["status"] == "unallocated_service_rr_4_4":
                t = "The service is not allocated in Region 1 for this band and operates under RR No. 4.4."
                if t not in caveats:
                    caveats.append(t)

        stations = []
        for c in cases[:MAX_STATION_ROWS]:
            fs, cr = c["finnish_station"], c["result"]
            stations.append({
                "id": fs["station_number"],
                "latitude": fs["latitude"],
                "longitude": fs["longitude"],
                "band": band(fs.get("protected_band") or {}),
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
                continue  # listed below for every affected station
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
            "administration": sp["administration"],
            "administrationName": admin(sp["administration"]),
            "name": clean(", ".join(worst.get("satellite_names") or [f"Notice {notice_id}"])),
            "provision": PROVISIONS.get(sp.get("provision"), sp.get("provision") or ""),
            "publicationDate": safe_date(sp.get("publication_date")),
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
            "assumptions": [clean(a) for a in worst.get("assumptions", [])],
            "caveats": caveats,
            "stationsAffected": affected,
            "casesOfConcern": len(cases),
            "stations": stations,
            "sourceRows": rows,
        })

    issue = {
        "id": issue_id,
        "label": f"IFIC {issue_no}",
        "kind": "Space",
        "counts": summary["counts"],
        "noticesOfConcern": len(notices),
        "runId": summary["run"]["run_id"][:12],
    }
    return issue, notices


def rows_text(nums: list[int], limit: int = 12) -> str:
    shown = ", ".join(str(n) for n in nums[:limit])
    return shown + (f" and {len(nums) - limit} more" if len(nums) > limit else "")


# ------------------------------------------------------------ terrestrial


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
        "The border geometry is the generalised GISCO coastline, not the outer limit of Finland's territorial sea, so sea path distances may be too long and field strengths too low.",
    ]
    if crit.get("challenge_extension"):
        caveats.append(clean(crit["challenge_extension"]))

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
            "administration": f["administration"],
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
            "caveats": caveats,
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
        "counts": counts,
        "noticesOfConcern": len(notices),
        "runId": str(summary.get("run_id", ""))[:12],
    }
    trends = None
    tf = folder / "terrestrial_trends.json"
    if tf.exists():
        t = json.loads(tf.read_text(encoding="utf8"))
        trends = {
            "previous": f"BR IFIC {summary.get('previous_issue', '')}",
            "current": f"BR IFIC {issue_no}",
            "administrations": [
                {"label": a["administration"], "previous": a["previous"], "current": a["current"]}
                for a in t.get("administration_activity", [])
            ],
            "bands": [
                {"label": clean(b["band"]), "previous": b["previous"], "current": b["current"]}
                for b in t.get("band_activity", [])
            ],
        }
    return issue, notices, trends


def rounded(value):
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


# ------------------------------------------------------------------ main


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
        "issues": issues,
        "notices": notices,
        "trends": trends,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(rounded(data), ensure_ascii=False), encoding="utf8")
    print(f"Wrote {TARGET.relative_to(ROOT)}: {len(issues)} issues, {len(notices)} notices of concern")


if __name__ == "__main__":
    main()
