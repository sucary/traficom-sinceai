from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
from importlib.resources import files

from .p1546_model import MODEL_VERSION, erp_kw_from_radiated_power, field_strength_dbuv_m
from .terrestrial_criteria import CRITERION, threshold_dbuv_m


METHOD_VERSION = "terrestrial-land-mobile-v1.8"
FINLAND_ADMINISTRATION = "FIN"
LAND_MOBILE_CLASSES = {"FB", "ML"}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"Required prepared table is missing: {path}")
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _dataset_directory(prepared: Path, item: dict) -> Path:
    return prepared / item["output_directory"]


def _terrestrial_datasets(prepared: Path) -> list[dict]:
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = []
    for item in manifest.get("datasets", []):
        tables = item.get("extraction", {}).get("tables", {})
        if item.get("status") == "extracted" and "fxm_terra" in tables:
            result.append(item)
    return sorted(result, key=lambda item: item.get("issue") or -1)


def select_consecutive_issues(prepared: Path, current_issue: int) -> tuple[dict | None, dict]:
    by_issue = {item.get("issue"): item for item in _terrestrial_datasets(prepared)}
    if current_issue not in by_issue:
        raise ValueError(
            f"Terrestrial issue {current_issue} is required; "
            f"available issues: {sorted(issue for issue in by_issue if issue is not None)}"
        )
    return by_issue.get(current_issue - 1), by_issue[current_issue]


def _publication_parts(directory: Path, issue: int) -> dict[int, set[str]]:
    parts: dict[int, set[str]] = defaultdict(set)
    for record in _read_jsonl(directory / "fxm_pub_hist.jsonl"):
        raw = record["raw"]
        if int(raw.get("pub_no") or -1) == issue:
            parts[int(raw["terrakey"])].add(str(raw.get("pub_part") or ""))
    return parts


def classify_event(raw: dict, current_parts: set[str]) -> str:
    amendment = str(raw.get("amend_type") or "").strip().upper()
    modification = str(raw.get("mod_type") or "").strip().upper()
    if "3" in current_parts or "WITHDRAW" in amendment or "WITHDRAW" in modification:
        return "withdrawn"
    if not current_parts:
        return "not_published_in_issue"
    unchanged = {"", "NOT AMENDED", "NOT MODIFY", "RECORDED", "NONE"}
    if amendment not in unchanged or modification not in unchanged:
        return "modified"
    if "1" in current_parts:
        return "new"
    if "2" in current_parts:
        return "recorded"
    return "not_published_in_issue"


def _identity(raw: dict) -> str:
    assignment = str(raw.get("assgn_id") or "").strip()
    if assignment:
        return f"{raw.get('adm') or ''}:{assignment}"
    return f"terrakey:{raw.get('terrakey')}"


def _index(records: list[dict], field: str) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        value = record["raw"].get(field)
        if value is not None:
            result[int(value)].append(record)
    return result


def _geometry_segments() -> tuple[list[tuple], dict]:
    resource = files("app.reference").joinpath("finland_assessment_boundary.geojson")
    document = json.loads(resource.read_text(encoding="utf-8"))
    lines: list[tuple[list[tuple[float, float]], str, str, str]] = []

    def add_line(coordinates, kind, path_zone, section_id):
        points = [(float(latitude), float(longitude)) for longitude, latitude, *_ in coordinates]
        if len(points) >= 2:
            lines.append((points, kind, path_zone, section_id))

    for feature in document["features"]:
        geometry = feature["geometry"]
        kind = feature["properties"]["kind"]
        path_zone = feature["properties"]["path_zone"]
        if geometry["type"] == "LineString":
            add_line(geometry["coordinates"], kind, path_zone, feature["id"])
        elif geometry["type"] == "MultiLineString":
            for index, line in enumerate(geometry["coordinates"], 1):
                add_line(line, kind, path_zone, f"{feature['id']}:{index}")
        else:
            raise ValueError(f"Unsupported assessment geometry type: {geometry['type']}")
    segments = []
    for line, kind, path_zone, section_id in lines:
        for start, end in zip(line, line[1:]):
            if start != end:
                segments.append((start, end, kind, path_zone, section_id))
    segment_counts = Counter(segment[2] for segment in segments)
    source = {
        "title": document["metadata"]["title"],
        "sources": document["metadata"]["sources"],
        "retrieved": document["metadata"]["retrieved"],
        "license": document["metadata"]["license"],
        "coverage": document["metadata"]["coverage"],
        "line_count": len(lines),
        "point_count": len({point for line, _, _, _ in lines for point in line}),
        "segment_count": len(segments),
        "segment_counts": dict(sorted(segment_counts.items())),
        "path_zone_rule": {
            "land_border": "Land",
            "territorial_sea_outer_limit": "Cold",
            "protected_station": "maximum of Land and Cold when the path composition is unknown",
        },
        "nearest_point_method": (
            "Nearest point anywhere on the boundary: every segment (straight in longitude/latitude "
            "per GeoJSON RFC 7946 3.1.1) is ranked by a local equirectangular projection, and close "
            "candidates are refined by minimising the haversine distance along the segment."
        ),
        "limitation": (
            "Land-border WFS coordinates are rounded to three decimal places. Without terrain profiles, "
            "each boundary path is treated as homogeneous and protected-station paths use the larger "
            "of the Land and Cold-sea predictions."
        ),
    }
    return segments, source


def _protected_stations(prepared: Path) -> list[dict]:
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    stations = []
    for item in manifest.get("datasets", []):
        if not str(item.get("file", "")).lower().endswith(".xlsx"):
            continue
        path = prepared / item["output_directory"] / "stations.jsonl"
        if not path.is_file():
            continue
        for record in _read_jsonl(path):
            if record.get("latitude") is None or record.get("longitude") is None:
                continue
            centers: dict[float, list[str]] = {}
            for role, key in (("rx", "rx_frequency_hz"), ("tx", "tx_frequency_hz")):
                if record.get(key) is not None:
                    centers.setdefault(float(record[key]), []).append(role)
            bandwidth = float(record.get("effective_bandwidth_hz") or record.get("channel_bandwidth_hz") or 0)
            for center, roles in centers.items():
                stations.append(
                    {
                        "latitude": float(record["latitude"]),
                        "longitude": float(record["longitude"]),
                        "frequency_min_hz": center - bandwidth / 2,
                        "frequency_max_hz": center + bandwidth / 2,
                        "frequency_role": "_".join(roles),
                        "station_number": record.get("station_number"),
                        "source_row": record.get("source_row"),
                        "dataset_id": record.get("dataset_id"),
                    }
                )
    return stations


def _matching_protected_stations(stations: list[dict], frequency_hz: float) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for station in stations:
        if not station["frequency_min_hz"] <= frequency_hz <= station["frequency_max_hz"]:
            continue
        key = (station.get("station_number"), station["latitude"], station["longitude"])
        if key not in grouped:
            grouped[key] = {
                **station,
                "station_source_rows": [],
                "station_dataset_ids": [],
                "matching_frequency_ranges_hz": [],
                "matching_frequency_roles": [],
            }
        match = grouped[key]
        match["station_source_rows"].append(station.get("source_row"))
        match["station_dataset_ids"].append(station.get("dataset_id"))
        match["matching_frequency_ranges_hz"].append(
            [station["frequency_min_hz"], station["frequency_max_hz"]]
        )
        if station.get("frequency_role"):
            match["matching_frequency_roles"].append(station["frequency_role"])
    for match in grouped.values():
        match["station_source_rows"] = sorted(set(match["station_source_rows"]))
        match["station_dataset_ids"] = sorted(set(match["station_dataset_ids"]))
        match["matching_frequency_ranges_hz"] = sorted(set(
            tuple(value) for value in match["matching_frequency_ranges_hz"]
        ))
        match["matching_frequency_roles"] = sorted(set(match["matching_frequency_roles"]))
    return sorted(grouped.values(), key=lambda item: (
        str(item.get("station_number") or ""), item["latitude"], item["longitude"]
    ))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_on(start, end, t):
    return (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)


def _projected_parameter(latitude, longitude, start, end):
    scale = math.cos(math.radians(latitude))
    ax, ay = (start[1] - longitude) * scale, start[0] - latitude
    bx, by = (end[1] - longitude) * scale, end[0] - latitude
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length == 0:
        return 0.0, math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / length))
    return t, math.hypot(ax + t * dx, ay + t * dy)


def nearest_point_on_segment(latitude: float, longitude: float, start, end) -> tuple[tuple[float, float], float]:
    def distance(t):
        return haversine_km(latitude, longitude, *_point_on(start, end, t))

    t0, _ = _projected_parameter(latitude, longitude, start, end)
    grid = sorted({0.0, 1.0, t0, *(i / 64 for i in range(65))})
    best = min(grid, key=distance)
    lower, upper = max(0.0, best - 1 / 64), min(1.0, best + 1 / 64)
    ratio = (math.sqrt(5) - 1) / 2
    c, d = upper - ratio * (upper - lower), lower + ratio * (upper - lower)
    fc, fd = distance(c), distance(d)
    for _ in range(60):
        if fc <= fd:
            upper, d, fd = d, c, fc
            c = upper - ratio * (upper - lower)
            fc = distance(c)
        else:
            lower, c, fc = c, d, fd
            d = lower + ratio * (upper - lower)
            fd = distance(d)
    t = min((best, (lower + upper) / 2), key=distance)
    point = _point_on(start, end, t)
    return point, distance(t)


def nearest_assessment_point(latitude: float, longitude: float, segments, include_metadata: bool = False):
    if not segments:
        raise ValueError("Boundary geometry has no segments")
    approximate = [(_projected_parameter(latitude, longitude, segment[0], segment[1])[1], index)
                   for index, segment in enumerate(segments)]
    best_approximate = min(value for value, _ in approximate)
    limit = best_approximate * 1.25 + 2.0 / 111.0
    best_point, best_distance, best_segment = None, math.inf, None
    for value, index in approximate:
        if value > limit:
            continue
        segment = segments[index]
        point, distance = nearest_point_on_segment(latitude, longitude, segment[0], segment[1])
        if distance < best_distance:
            best_point, best_distance, best_segment = point, distance, segment
    metadata = {
        "kind": best_segment[2] if len(best_segment) > 2 else "finland_assessment_boundary",
        "path_zone": best_segment[3] if len(best_segment) > 3 else "Land",
    }
    if len(best_segment) > 4:
        metadata["section_id"] = best_segment[4]
    return (best_point, best_distance, metadata) if include_metadata else (best_point, best_distance)


def nearest_assessment_points_by_section(latitude: float, longitude: float, segments) -> list[dict]:
    sections: dict[str, list[tuple]] = defaultdict(list)
    for index, segment in enumerate(segments):
        section_id = segment[4] if len(segment) > 4 else f"boundary:{index}"
        sections[section_id].append(segment)
    points = []
    for section_id, section_segments in sorted(sections.items()):
        point, distance, metadata = nearest_assessment_point(
            latitude, longitude, section_segments, include_metadata=True
        )
        points.append({
            **metadata,
            "section_id": section_id,
            "latitude": point[0],
            "longitude": point[1],
            "distance_km": distance,
        })
    return points


def _power_and_height(antennas: list[dict], heights: list[dict]) -> tuple[dict | None, list[str]]:
    candidates = []
    problems = []
    for record in antennas:
        raw = record["raw"]
        if str(raw.get("tx_rx") or "").upper() != "TX" or raw.get("pwr_dbw") is None:
            continue
        try:
            erp_kw, delta_db = erp_kw_from_radiated_power(raw["pwr_dbw"], raw.get("pwr_eiv"))
        except ValueError:
            continue
        height_values = [
            float(value)
            for value in (raw.get("eff_hgtmax"), raw.get("hgt_agl"))
            if value is not None and float(value) > 0
        ]
        antenna_key = raw.get("ant_key")
        matching_height_rows = [
            item for item in heights
            if item["raw"].get("ant_key") == antenna_key
            and item["raw"].get("eff_hgt") is not None
            and float(item["raw"]["eff_hgt"]) > 0
        ]
        height_values.extend(float(item["raw"]["eff_hgt"]) for item in matching_height_rows)
        if not height_values:
            problems.append("missing_effective_tx_height")
            continue
        candidates.append(
            {
                "erp_kw": erp_kw,
                "power_dbw": float(raw["pwr_dbw"]),
                "power_type": raw.get("pwr_eiv"),
                "erp_conversion_db": delta_db,
                "effective_tx_height_m": max(height_values),
                "antenna_source_row": record["source_row"],
                "antenna_height_source_rows": [item["source_row"] for item in matching_height_rows],
            }
        )
    if not candidates:
        return None, sorted(set(problems or ["missing_usable_erp_and_antenna_height"]))
    return max(candidates, key=lambda item: (item["erp_kw"], item["effective_tx_height_m"])), []


def _write_jsonl(path: Path, records: list[dict]):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: Path, records: list[dict]):
    fields = [
        "event", "result", "administration", "assignment_id", "terrakey", "frequency_mhz",
        "assessment_kind", "path_zone", "field_strength_dbuv_m", "threshold_dbuv_m", "margin_db", "distance_km",
        "tx_latitude", "tx_longitude", "assessment_latitude", "assessment_longitude",
        "missing_inputs", "source_row",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            flat = dict(record)
            flat["missing_inputs"] = ";".join(record.get("missing_inputs", []))
            writer.writerow(flat)


def _trend_summary(previous_rows: list[dict], current_rows: list[dict], previous_parts: dict, current_parts: dict) -> dict:
    def counts(rows, issue_parts=None):
        selected = []
        for record in rows:
            raw = record["raw"]
            if raw.get("stn_cls") not in LAND_MOBILE_CLASSES or raw.get("adm") == FINLAND_ADMINISTRATION:
                continue
            if issue_parts is not None and not issue_parts.get(int(raw["terrakey"])):
                continue
            selected.append(raw)
        bands = Counter(f"{int(float(r['freq_assgn']) // 100) * 100}-{int(float(r['freq_assgn']) // 100) * 100 + 100} MHz"
                        for r in selected if r.get("freq_assgn") is not None)
        return Counter(r.get("adm") or "UNKNOWN" for r in selected), bands

    old_admin, old_band = counts(previous_rows, previous_parts)
    new_admin, new_band = counts(current_rows, current_parts)
    return {
        "administration_activity": [
            {"administration": key, "previous": old_admin[key], "current": new_admin[key],
             "delta": new_admin[key] - old_admin[key]}
            for key in sorted(set(old_admin) | set(new_admin), key=lambda key: abs(new_admin[key] - old_admin[key]), reverse=True)[:10]
        ],
        "band_activity": [
            {"band": key, "previous": old_band[key], "current": new_band[key],
             "delta": new_band[key] - old_band[key]}
            for key in sorted(set(old_band) | set(new_band), key=lambda key: abs(new_band[key] - old_band[key]), reverse=True)[:10]
        ],
    }


RR_SOURCE = {"document": "ITU Radio Regulations, Edition of 2024, Volume 1 (Articles)",
             "file": "docs/reference/itu-rr-2024/RR-2024-Vol1-Articles-E.pdf"}
REGULATORY_FRAMEWORK = [
    {"level": "ITU", "provision": "RR No. 4.3", "printed_page": 31, "pdf_page": 41,
     "role": "A new or changed assignment must avoid harmful interference to services using frequencies "
             "assigned in accordance with the Table of Frequency Allocations and the Radio Regulations.", **RR_SOURCE},
    {"level": "ITU", "provision": "RR Nos. 11.2 and 11.3", "printed_page": 226, "pdf_page": 236,
     "role": "An assignment capable of causing harmful interference to a service of another administration "
             "must be notified to the Radiocommunication Bureau; such notices are what the terrestrial BR IFIC "
             "publishes and what this screening reviews.", **RR_SOURCE},
    {"level": "ITU", "provision": "RR No. 8.3", "printed_page": 207, "pdf_page": 217,
     "role": "An assignment recorded in the Master Register with a favourable finding has the right to "
             "international recognition: other administrations must take it into account. Reviewing new "
             "foreign notices is therefore time-relevant for Finland.", **RR_SOURCE},
    {"level": "ITU", "provision": "RR No. 6.1", "printed_page": 201, "pdf_page": 211,
     "role": "Administrations may conclude special agreements; regional cross-border coordination criteria "
             "such as CEPT recommendations are applied within this framework.", **RR_SOURCE},
    {"level": "CEPT/ECC", "provision": "ECC Recommendation T/R 25-08, A.1.2.3 (6 June 2025)",
     "url": "https://docdb.cept.org/download/4789",
     "role": "Planning criteria and cross-border coordination of frequencies for land mobile systems: the "
             "border-line field-strength trigger used as the coordination criterion (above 470 MHz the "
             "above-400 MHz value, per the challenge Q&A)."},
    {"level": "National", "provision": "Traficom Regulation M4 (4 AG/2026M), Frequency Allocation Table",
     "file": "docs/reference/traficom-m4/Taajuusjakotaulukko_api_v13_2026-11-07.json",
     "role": "Services in use or intended to be used in Finland per band. Each finding records whether Finland "
             "lists the mobile service at that frequency, that is, whether there is national land mobile use "
             "to protect."},
]


def national_context(frequency_mhz: float) -> dict:
    from ..reference.allocations import m4_assessment

    hz = int(round(float(frequency_mhz) * 1_000_000))
    m4 = m4_assessment(["MOBILE"], set(), hz, hz)
    return {"mobile_in_finland": m4["partner_in_finland"],
            "m4_bands": [{"band": b["m4_band"], "services": b["services"]} for b in m4["m4_bands"]]}


NEIGHBOUR_KM = 1000.0
NEW_CLASS_MIN = 3
NEAR_BORDER_KM = 50.0
OUTLIER_Z, OUTLIER_MIN_GROUP = 3.5, 8
OUTLIER_MIN_DIFFERENCE = {"erp_dbw": 6.0, "height_m": 30.0}
OUTLIER_MIN_RATIO = {"bandwidth_khz": 2.0}
BOUNDARY_KINDS = {"land_border", "territorial_sea_outer_limit"}
ANOMALY_RULES = {
    "neighbour": f"An administration with at least one base-station (FB) transmitter in this issue within "
                 f"{NEIGHBOUR_KM:g} km of the Finnish land border or territorial-sea limit (the P.1546 range).",
    "filing_summary": "Per neighbour: new, modified and withdrawn base stations in this issue, how many are within "
                      "range, and how many exceed the screening threshold.",
    "new_activity_near_border": f"New base stations of a neighbour within {NEAR_BORDER_KM:g} km of the Finnish land "
                                "border or territorial-sea limit.",
    "parameter_outlier": f"A neighbour's base station whose ERP, effective antenna height or bandwidth has a robust "
                         f"z-score above {OUTLIER_Z:g} (0.6745 x deviation from the median / MAD, Iglewicz and "
                         f"Hoaglin) among all foreign base stations in this issue in its 100 MHz band (at least "
                         f"{OUTLIER_MIN_GROUP}), and differs from the median by at least 6 dB (ERP), 30 m (height) "
                         "or a factor of 2 (bandwidth).",
    "new_station_class": f"A neighbour uses a land-mobile station class absent from its notices in the previous issue "
                         f"(at least {NEW_CLASS_MIN} notices).",
}


def _boundary_distance(result) -> float | None:
    distances = [a["distance_km"] for a in result.get("assessments", [])
                 if a.get("kind") in BOUNDARY_KINDS and a.get("distance_km") is not None]
    return min(distances) if distances else None


def _band_label(frequency_mhz) -> str:
    low = int(float(frequency_mhz) // 100) * 100
    return f"{low}-{low + 100} MHz"


def _robust_outliers(values: list[tuple[str, float]]) -> list[tuple[str, float, float, float]]:
    if len(values) < OUTLIER_MIN_GROUP:
        return []
    numbers = sorted(v for _, v in values)
    median = numbers[len(numbers) // 2] if len(numbers) % 2 else sum(numbers[len(numbers) // 2 - 1:len(numbers) // 2 + 1]) / 2
    deviations = sorted(abs(v - median) for v in numbers)
    mad = deviations[len(deviations) // 2] if len(deviations) % 2 else sum(deviations[len(deviations) // 2 - 1:len(deviations) // 2 + 1]) / 2
    if mad > 0:
        score = lambda value: 0.6745 * (value - median) / mad
    else:
        mean_ad = sum(deviations) / len(deviations)
        if mean_ad == 0:
            return []
        score = lambda value: (value - median) / (1.253314 * mean_ad)
    return [(item, value, median, score(value)) for item, value in values if abs(score(value)) > OUTLIER_Z]


def _anomalies(previous_rows, current_rows, previous_parts, current_parts, results) -> list[dict]:
    neighbours = set()
    for r in results:
        distance = _boundary_distance(r)
        if distance is not None and distance <= NEIGHBOUR_KM:
            neighbours.add(r["administration"])
    by_admin = {adm: [r for r in results if r["administration"] == adm] for adm in neighbours}
    flags = []

    def order(adm):
        return (-sum(r["result"] == "exceeds_threshold" for r in by_admin[adm]), adm)

    ranked = sorted(neighbours, key=order)
    for adm in ranked:
        rows = by_admin[adm]
        events = Counter(r["event"] for r in rows)
        in_range = [r for r in rows if r["result"] in {"exceeds_threshold", "near_threshold", "below_threshold"}]
        exceeding = sorted((r for r in rows if r["result"] == "exceeds_threshold"), key=lambda r: -r["margin_db"])
        flags.append({"type": "filing_summary", "administration": adm, "subject": adm,
                      "reason": f"{adm}: {events['new']} new, {events['modified']} modified and {events['withdrawn']} "
                                f"withdrawn base stations; {len(in_range)} within range, {len(exceeding)} above the "
                                "screening threshold.",
                      "evidence": {"new": events["new"], "modified": events["modified"],
                                   "withdrawn": events["withdrawn"], "within_range": len(in_range),
                                   "exceeding": [{"assignment_id": r["assignment_id"],
                                                  "frequency_mhz": r["frequency_mhz"],
                                                  "margin_db": round(r["margin_db"], 2)} for r in exceeding]}})
        near = []
        for r in rows:
            distance = _boundary_distance(r)
            if r["event"] == "new" and distance is not None and distance <= NEAR_BORDER_KM:
                near.append((r, distance))
        near.sort(key=lambda item: item[1])
        if near:
            flags.append({"type": "new_activity_near_border", "administration": adm, "subject": adm,
                          "reason": f"{adm}: {len(near)} new base station(s) within {NEAR_BORDER_KM:g} km of the "
                                    "Finnish border or territorial-sea limit.",
                          "evidence": {"assignments": [
                              {"assignment_id": r["assignment_id"], "frequency_mhz": r["frequency_mhz"],
                               "distance_km": round(d, 1), "result": r["result"],
                               "margin_db": round(r["margin_db"], 2) if r.get("margin_db") is not None else None}
                              for r, d in near]}})

    groups = {}
    for res in results:
        if res.get("frequency_mhz") is None:
            continue
        g = groups.setdefault(_band_label(res["frequency_mhz"]), {"erp_dbw": [], "height_m": [], "bandwidth_khz": []})
        if res.get("erp_kw"):
            g["erp_dbw"].append((res["assignment_id"], 10 * math.log10(float(res["erp_kw"]) * 1000)))
        if res.get("effective_tx_height_m") is not None:
            g["height_m"].append((res["assignment_id"], float(res["effective_tx_height_m"])))
        bandwidth = (res.get("source_notice") or {}).get("bdwdth")
        if bandwidth is not None:
            g["bandwidth_khz"].append((res["assignment_id"], float(bandwidth)))
    by_id = {r["assignment_id"]: r for r in results}
    for band, metrics in sorted(groups.items()):
        for metric, values in metrics.items():
            for item, value, median, z in _robust_outliers(values):
                owner = by_id.get(item, {})
                if owner.get("administration") not in neighbours:
                    continue
                if metric in OUTLIER_MIN_DIFFERENCE and abs(value - median) < OUTLIER_MIN_DIFFERENCE[metric]:
                    continue
                ratio = OUTLIER_MIN_RATIO.get(metric)
                if ratio and median > 0 and 1 / ratio < value / median < ratio:
                    continue
                flags.append({"type": "parameter_outlier", "administration": owner["administration"],
                              "subject": item,
                              "reason": f"Assignment {item} in {band}: {metric} {value:.1f} against a band median of "
                                        f"{median:.1f} (robust z {z:+.1f}).",
                              "evidence": {"assignment_id": item, "band": band, "metric": metric,
                                           "frequency_mhz": owner.get("frequency_mhz"), "result": owner.get("result"),
                                           "value": round(value, 2), "band_median": round(median, 2),
                                           "robust_z": round(z, 2), "group_size": len(values)}})

    def selected(rows, issue_parts):
        return [record["raw"] for record in rows
                if record["raw"].get("stn_cls") in LAND_MOBILE_CLASSES
                and record["raw"].get("adm") in neighbours
                and issue_parts.get(int(record["raw"]["terrakey"]))]

    old_classes = {}
    for r in selected(previous_rows, previous_parts):
        old_classes.setdefault(r.get("adm"), set()).add(r.get("stn_cls"))
    new_class_counts = Counter((r.get("adm"), r.get("stn_cls")) for r in selected(current_rows, current_parts))
    for (adm, cls), n in sorted(new_class_counts.items(), key=lambda kv: str(kv[0])):
        if n >= NEW_CLASS_MIN and adm in old_classes and cls not in old_classes[adm]:
            flags.append({"type": "new_station_class", "administration": adm, "subject": f"{adm} {cls}",
                          "reason": f"{adm} has {n} {cls} notices in this issue and none in the previous one.",
                          "evidence": {"station_class": cls, "current": n}})
    rank = {adm: i for i, adm in enumerate(ranked)}
    kinds = ["filing_summary", "new_activity_near_border", "parameter_outlier", "new_station_class"]
    flags.sort(key=lambda f: (rank[f["administration"]], kinds.index(f["type"])))
    return flags


def run(prepared: Path, output: Path, current_issue: int = 3076, near_margin_db: float = 3.0) -> dict:
    previous_item, current_item = select_consecutive_issues(prepared, current_issue)
    current_dir = _dataset_directory(prepared, current_item)
    current_rows = _read_jsonl(current_dir / "fxm_terra.jsonl")
    if previous_item is not None:
        previous_dir = _dataset_directory(prepared, previous_item)
        previous_rows = _read_jsonl(previous_dir / "fxm_terra.jsonl")
        previous_parts = _publication_parts(previous_dir, current_issue - 1)
    else:
        previous_rows, previous_parts = [], {}
    previous_ids = {_identity(record["raw"]): record for record in previous_rows}
    parts = _publication_parts(current_dir, current_issue)
    antennas = _index(_read_jsonl(current_dir / "fxm_ant.jsonl"), "terrakey")
    heights = _index(_read_jsonl(current_dir / "fxm_ant_hgt.jsonl"), "terrakey")
    transmitters = _index(_read_jsonl(current_dir / "fxm_tx.jsonl"), "terrakey")
    geographies = {
        int(record["raw"]["geo_key"]): record
        for record in _read_jsonl(current_dir / "fxm_geo.jsonl")
        if record["raw"].get("geo_key") is not None
    }
    boundary_segments, geometry_source = _geometry_segments()
    protected_stations = _protected_stations(prepared)
    results = []

    for record in current_rows:
        raw = record["raw"]
        key = int(raw["terrakey"])
        event = classify_event(raw, parts.get(key, set()))
        if event not in {"new", "modified", "withdrawn"}:
            continue
        if (raw.get("adm") == FINLAND_ADMINISTRATION or raw.get("stn_cls") != "FB"
                or str(raw.get("stn_type") or "").upper() != "TX"):
            continue
        result = {
            "schema_version": 1,
            "method_version": METHOD_VERSION,
            "event": event,
            "result": "withdrawn" if event == "withdrawn" else "missing_input",
            "administration": raw.get("adm"),
            "assignment_id": raw.get("assgn_id"),
            "terrakey": key,
            "frequency_mhz": raw.get("freq_assgn"),
            "source_row": record["source_row"],
            "dataset_id": record["dataset_id"],
            "previous_issue_seen": (_identity(raw) in previous_ids) if previous_item is not None else None,
            "publication_parts": sorted(parts.get(key, set())),
            "missing_inputs": [],
            "source_notice": raw,
            "criterion": CRITERION,
            "model": {
                "name": MODEL_VERSION,
                "recommendation_url": "https://www.itu.int/rec/R-REC-P.1546-6-201908-I/en",
                "implementation_url": "https://github.com/eeveetza/Py1546",
                "implementation_commit": "e235629009ab1a12a33fc4a8fb5612f2883ecb5b",
                "time_percentage": 10,
                "location_percentage": 50,
                "receiver_height_m": 10,
                "receiver_clutter_height_m": 10,
                "receiver_area": "Rural",
                "path_zone": "assessment_specific",
                "path_zone_rule": geometry_source["path_zone_rule"],
                "terrain_profile_available": False,
            },
            "sources": [
                {"role": "criterion", "title": "ECC T/R 25-08 (6 June 2025)",
                 "url": "https://docdb.cept.org/download/4789"},
                {"role": "model", "title": "ITU-R P.1546-6",
                 "url": "https://www.itu.int/rec/R-REC-P.1546-6-201908-I/en"},
                {"role": "model_implementation", "title": "Py1546",
                 "url": "https://github.com/eeveetza/Py1546"},
                {"role": "notice_fields", "title": "Terrestrial BR IFIC Preface",
                 "url": "https://www.itu.int/en/ITU-R/terrestrial/brific/BRIFIC/Preface/PREFACE_EN.pdf"},
                *[
                    {"role": f"assessment_geometry_{source['role']}",
                     "title": f"{source['provider']} — {source['role'].replace('_', ' ')}",
                     "url": source["source_url"]}
                    for source in geometry_source["sources"]
                ],
            ],
        }
        if event == "withdrawn":
            results.append(result)
            continue
        frequency = raw.get("freq_assgn")
        if frequency is None:
            result["missing_inputs"].append("missing_frequency")
            results.append(result)
            continue
        result["national_context_m4"] = national_context(frequency)
        tx_rows = transmitters.get(key, [])
        geo_keys = [item["raw"].get("geo_key") for item in tx_rows]
        if not geo_keys and raw.get("geo_key") is not None:
            geo_keys = [raw.get("geo_key")]
        geo = next((geographies.get(int(value)) for value in geo_keys if value is not None and int(value) in geographies), None)
        if geo is None or geo["raw"].get("lat_dec") is None or geo["raw"].get("long_dec") is None:
            result["missing_inputs"].append("missing_transmitter_coordinates")
        technical, problems = _power_and_height(antennas.get(key, []), heights.get(key, []))
        result["missing_inputs"].extend(problems)
        if result["missing_inputs"]:
            results.append(result)
            continue
        latitude, longitude = float(geo["raw"]["lat_dec"]), float(geo["raw"]["long_dec"])
        boundary_points = nearest_assessment_points_by_section(latitude, longitude, boundary_segments)
        candidates = [
            {**boundary, "path_zone_candidates": [boundary["path_zone"]],
             "path_zone_basis": "official boundary section"}
            for boundary in boundary_points
        ]
        frequency_hz = float(frequency) * 1_000_000
        matching_stations = _matching_protected_stations(protected_stations, frequency_hz)
        for station in matching_stations:
            candidates.append(
                {"kind": "protected_station", "latitude": station["latitude"],
                 "longitude": station["longitude"],
                 "distance_km": haversine_km(latitude, longitude, station["latitude"], station["longitude"]),
                 "path_zone_candidates": ["Land", "Cold"],
                 "path_zone_basis": "maximum prediction because path composition is unknown",
                 "station_number": station["station_number"], "station_source_row": station["source_row"],
                 "station_dataset_id": station["dataset_id"],
                 "station_source_rows": station["station_source_rows"],
                 "station_dataset_ids": station["station_dataset_ids"],
                 "matching_frequency_ranges_hz": station["matching_frequency_ranges_hz"],
                 "matching_frequency_roles": station["matching_frequency_roles"]}
            )
        result.update({"tx_latitude": latitude, "tx_longitude": longitude,
                       "geography_source_row": geo["source_row"],
                       "transmitter_source_rows": [item["source_row"] for item in tx_rows], **technical})
        usable = [item for item in candidates if item["distance_km"] <= 1000]
        if not usable:
            result["result"] = "outside_model_distance"
            result["missing_inputs"].append("distance_above_1000_km")
            result["assessments"] = candidates
            results.append(result)
            continue
        try:
            threshold, bandwidth_correction = threshold_dbuv_m(float(frequency))
            for assessment in usable:
                model_distance = max(1.0, assessment["distance_km"])
                zone_results = []
                for path_zone in assessment["path_zone_candidates"]:
                    field, loss = field_strength_dbuv_m(
                        frequency_mhz=float(frequency), distance_km=model_distance,
                        effective_tx_height_m=technical["effective_tx_height_m"], erp_kw=technical["erp_kw"],
                        path_zone=path_zone)
                    zone_results.append({"path_zone": path_zone, "field_strength_dbuv_m": field,
                                         "basic_transmission_loss_db": loss})
                selected = max(zone_results, key=lambda item: item["field_strength_dbuv_m"])
                assessment.update(
                    {**selected, "path_zone_results": zone_results,
                     "threshold_dbuv_m": threshold, "margin_db": selected["field_strength_dbuv_m"] - threshold,
                     "distance_clamped_to_1_km": assessment["distance_km"] < 1}
                )
        except ValueError as error:
            result["missing_inputs"].append(str(error))
            results.append(result)
            continue
        worst = max(usable, key=lambda item: item["margin_db"])
        margin = worst["margin_db"]
        result.update(
            {
                "assessment_kind": worst["kind"],
                "assessment_latitude": worst["latitude"],
                "assessment_longitude": worst["longitude"],
                "path_zone": worst["path_zone"],
                "distance_km": worst["distance_km"],
                "field_strength_dbuv_m": worst["field_strength_dbuv_m"],
                "basic_transmission_loss_db": worst["basic_transmission_loss_db"],
                "threshold_dbuv_m": threshold,
                "bandwidth_correction_db": bandwidth_correction,
                "margin_db": margin,
                "assessments": candidates,
                "result": "exceeds_threshold" if margin > 0 else ("near_threshold" if margin >= -near_margin_db else "below_threshold"),
            }
        )
        results.append(result)

    output.mkdir(parents=True, exist_ok=True)
    findings = [item for item in results if item["result"] != "outside_model_distance"]
    prefix = f"terrestrial_ific{current_issue}"
    _write_jsonl(output / f"{prefix}_screening.jsonl", results)
    _write_jsonl(output / f"{prefix}_findings.jsonl", findings)
    _write_csv(output / f"{prefix}_findings.csv", findings)
    exposed_stations = [
        {
            "assignment_id": result["assignment_id"],
            "terrakey": result["terrakey"],
            "administration": result["administration"],
            "frequency_mhz": result["frequency_mhz"],
            **assessment,
        }
        for result in results
        for assessment in result.get("assessments", [])
        if assessment.get("kind") == "protected_station" and assessment.get("margin_db", -math.inf) > 0
    ]
    exposed_stations.sort(key=lambda item: (-item["margin_db"], str(item.get("station_number") or "")))
    (output / "terrestrial_exposed_stations.json").write_text(
        json.dumps(exposed_stations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    trends = (_trend_summary(previous_rows, current_rows, previous_parts, parts) if previous_item is not None
              else {"administration_activity": [], "band_activity": []})
    trends["previous_issue_available"] = previous_item is not None
    trends["anomaly_rules"] = ANOMALY_RULES
    trends["anomalies"] = _anomalies(previous_rows, current_rows, previous_parts, parts, results)
    (output / "terrestrial_trends.json").write_text(json.dumps(trends, indent=2) + "\n", encoding="utf-8")
    counts = Counter(item["result"] for item in results)
    summary = {
        "schema_version": 1,
        "status": "completed",
        "method_version": METHOD_VERSION,
        "previous_issue": current_issue - 1 if previous_item is not None else None,
        "current_issue": current_issue,
        "input_datasets": [
            {"file": item["file"], "dataset_id": item["dataset_id"], "issue": item["issue"]}
            for item in (previous_item, current_item) if item is not None
        ],
        "counts": dict(sorted(counts.items())),
        "screened_event_count": len(results),
        "finding_count": len(findings),
        "boundary_section_count": geometry_source["line_count"],
        "boundary_assessment_candidate_count": sum(
            assessment.get("kind") in {"land_border", "territorial_sea_outer_limit"}
            for result in results for assessment in result.get("assessments", [])
        ),
        "protected_station_candidate_count": sum(
            assessment.get("kind") == "protected_station"
            for result in results for assessment in result.get("assessments", [])
        ),
        "protected_station_assessment_count": sum(
            assessment.get("kind") == "protected_station" and "field_strength_dbuv_m" in assessment
            for result in results for assessment in result.get("assessments", [])
        ),
        "distinct_protected_station_candidate_count": len({
            assessment.get("station_number")
            for result in results for assessment in result.get("assessments", [])
            if assessment.get("kind") == "protected_station"
        }),
        "exposed_protected_station_count": len({
            assessment.get("station_number")
            for result in results for assessment in result.get("assessments", [])
            if assessment.get("kind") == "protected_station" and assessment.get("margin_db", -math.inf) > 0
        }),
        "exposed_protected_station_case_count": len(exposed_stations),
        "model": MODEL_VERSION,
        "criterion": CRITERION,
        "regulatory_framework": REGULATORY_FRAMEWORK,
        "anomaly_count": len(trends["anomalies"]),
        "assessment_geometry": geometry_source,
        "assumptions": [
            "Foreign FB transmitting/base stations are calculated; ML receiving land-mobile rows remain in trend counts.",
            "The true nearest point on every official NLS land-border and Traficom territorial-sea line section "
            "is screened (projection onto every segment, not the nearest vertex); the worst calculated field, "
            "rather than the globally shortest path, governs.",
            "Every co-frequency Finnish station in the supplied workbook is screened as a supplemental assessment "
            "point, matching on both its RX and TX frequency (Traficom Q&A: TX frequencies are also received in "
            "Finland); exposed stations are written to terrestrial_exposed_stations.json.",
            "Land-border assessments use the P.1546 Land zone and territorial-sea outer-limit assessments use "
            "the Cold-sea zone. Protected-station paths retain the larger Land/Cold prediction because their "
            "land/sea composition is unknown.",
            "Paths are homogeneous screening proxies with rural 10 m receiver clutter and no terrain profile.",
            "Maximum available ERP and effective antenna height are used for conservative screening.",
            "No bandwidth conversion is applied because occupied bandwidth is not proven to be channel spacing with uniform spectral power.",
            "A threshold exceedance is an expert-review trigger, not proof of harmful interference.",
        ],
    }
    run_material = json.dumps(summary, sort_keys=True).encode()
    summary["run_id"] = hashlib.sha256(run_material).hexdigest()
    (output / "terrestrial_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
