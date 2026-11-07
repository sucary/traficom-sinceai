"""Terrestrial BR IFIC land-mobile screening and P.1546 calculation pipeline."""

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


METHOD_VERSION = "terrestrial-land-mobile-v1.1"
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


def select_consecutive_issues(prepared: Path, current_issue: int) -> tuple[dict, dict]:
    by_issue = {item.get("issue"): item for item in _terrestrial_datasets(prepared)}
    if current_issue not in by_issue or current_issue - 1 not in by_issue:
        raise ValueError(
            f"Terrestrial issues {current_issue - 1} and {current_issue} are required; "
            f"available issues: {sorted(issue for issue in by_issue if issue is not None)}"
        )
    return by_issue[current_issue - 1], by_issue[current_issue]


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


def _geometry_segments() -> tuple[list[tuple[tuple[float, float], tuple[float, float]]], dict]:
    """Boundary line segments ((lat, lon), (lat, lon)) of every GISCO ring, in source order.

    Rings are kept separate so that only consecutive vertices of the same ring form a
    segment; the closing segment of an open ring is added.
    """
    resource = files("app.reference").joinpath("finland_gisco_2024_10m.geojson")
    document = json.loads(resource.read_text(encoding="utf-8"))
    ring_list: list[list[tuple[float, float]]] = []

    def rings(coordinates):
        if not coordinates:
            return
        if isinstance(coordinates[0][0], (int, float)):
            ring_list.append([(float(latitude), float(longitude)) for longitude, latitude, *_ in coordinates])
        else:
            for child in coordinates:
                rings(child)

    for feature in document["features"]:
        rings(feature["geometry"]["coordinates"])
    segments = []
    for ring in ring_list:
        if ring and ring[0] != ring[-1]:
            ring = [*ring, ring[0]]
        for start, end in zip(ring, ring[1:]):
            if start != end:
                segments.append((start, end))
    source = {
        "title": "GISCO Countries 2024 - Finland, 1:10 million, EPSG:4326",
        "url": (
            "https://gisco-services.ec.europa.eu/distribution/v2/countries/distribution/"
            "FI-region-10m-4326-2024.geojson"
        ),
        "ring_count": len(ring_list),
        "point_count": len({point for ring in ring_list for point in ring}),
        "segment_count": len(segments),
        "nearest_point_method": (
            "Nearest point anywhere on the boundary: every segment (straight in longitude/latitude "
            "per GeoJSON RFC 7946 3.1.1) is ranked by a local equirectangular projection, and close "
            "candidates are refined by minimising the haversine distance along the segment."
        ),
        "limitation": (
            "Generalised national boundary/coastline screening geometry; it is not a "
            "legal definition of the outer limit of Finland's territorial sea."
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
            centers = {record.get("rx_frequency_hz") or record.get("tx_frequency_hz")}
            centers.discard(None)
            bandwidth = float(record.get("effective_bandwidth_hz") or record.get("channel_bandwidth_hz") or 0)
            for center in centers:
                stations.append(
                    {
                        "latitude": float(record["latitude"]),
                        "longitude": float(record["longitude"]),
                        "frequency_min_hz": float(center) - bandwidth / 2,
                        "frequency_max_hz": float(center) + bandwidth / 2,
                        "station_number": record.get("station_number"),
                        "source_row": record.get("source_row"),
                        "dataset_id": record.get("dataset_id"),
                    }
                )
    return stations


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_on(start, end, t):
    return (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)


def _projected_parameter(latitude, longitude, start, end):
    """Segment parameter of the nearest point in a local equirectangular projection.

    GeoJSON edges are straight in longitude/latitude (RFC 7946, 3.1.1), so they stay
    straight under this affine projection centred on the query point.
    """
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
    """Nearest point to (latitude, longitude) on a boundary segment, and its distance in km.

    The segment is the straight longitude/latitude line between two GeoJSON positions.
    The haversine distance is minimised along it: a fine sample around the projected
    estimate, then golden-section refinement to sub-metre precision.
    """
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


def nearest_assessment_point(latitude: float, longitude: float, segments):
    """True nearest point anywhere along the boundary: the minimum over every segment.

    A cheap projected distance ranks all segments; every segment within 25 % + 2 km of the
    best projected distance is then refined exactly, so no candidate is dropped by
    projection error.
    """
    if not segments:
        raise ValueError("Boundary geometry has no segments")
    approximate = [(_projected_parameter(latitude, longitude, start, end)[1], index)
                   for index, (start, end) in enumerate(segments)]
    best_approximate = min(value for value, _ in approximate)
    limit = best_approximate * 1.25 + 2.0 / 111.0
    best_point, best_distance = None, math.inf
    for value, index in approximate:
        if value > limit:
            continue
        point, distance = nearest_point_on_segment(latitude, longitude, *segments[index])
        if distance < best_distance:
            best_point, best_distance = point, distance
    return best_point, best_distance


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
        "assessment_kind", "field_strength_dbuv_m", "threshold_dbuv_m", "margin_db", "distance_km",
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


def run(prepared: Path, output: Path, current_issue: int = 3076, near_margin_db: float = 3.0) -> dict:
    previous_item, current_item = select_consecutive_issues(prepared, current_issue)
    previous_dir = _dataset_directory(prepared, previous_item)
    current_dir = _dataset_directory(prepared, current_item)
    previous_rows = _read_jsonl(previous_dir / "fxm_terra.jsonl")
    current_rows = _read_jsonl(current_dir / "fxm_terra.jsonl")
    previous_ids = {_identity(record["raw"]): record for record in previous_rows}
    previous_parts = _publication_parts(previous_dir, current_issue - 1)
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
        # FB is the transmitting/base-station class in the land mobile service.
        # ML rows are receiving land-mobile stations and remain in the trend
        # analysis, but cannot be an interfering transmitter calculation.
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
            "previous_issue_seen": _identity(raw) in previous_ids,
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
                "path_zone": "Land",
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
                {"role": "assessment_geometry", "title": "GISCO Countries 2024 - Finland",
                 "url": geometry_source["url"]},
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
        point, distance = nearest_assessment_point(latitude, longitude, boundary_segments)
        candidates = [{"kind": "finland_boundary", "latitude": point[0], "longitude": point[1],
                       "distance_km": distance}]
        frequency_hz = float(frequency) * 1_000_000
        matching_stations = [item for item in protected_stations
                             if item["frequency_min_hz"] <= frequency_hz <= item["frequency_max_hz"]]
        if matching_stations:
            station = min(matching_stations, key=lambda item: haversine_km(
                latitude, longitude, item["latitude"], item["longitude"]))
            candidates.append(
                {"kind": "protected_station", "latitude": station["latitude"],
                 "longitude": station["longitude"],
                 "distance_km": haversine_km(latitude, longitude, station["latitude"], station["longitude"]),
                 "station_number": station["station_number"], "station_source_row": station["source_row"],
                 "station_dataset_id": station["dataset_id"]}
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
                field, loss = field_strength_dbuv_m(
                    frequency_mhz=float(frequency), distance_km=model_distance,
                    effective_tx_height_m=technical["effective_tx_height_m"], erp_kw=technical["erp_kw"])
                assessment.update(
                    {"field_strength_dbuv_m": field, "basic_transmission_loss_db": loss,
                     "threshold_dbuv_m": threshold, "margin_db": field - threshold,
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
    trends = _trend_summary(previous_rows, current_rows, previous_parts, parts)
    (output / "terrestrial_trends.json").write_text(json.dumps(trends, indent=2) + "\n", encoding="utf-8")
    counts = Counter(item["result"] for item in results)
    summary = {
        "schema_version": 1,
        "status": "completed",
        "method_version": METHOD_VERSION,
        "previous_issue": current_issue - 1,
        "current_issue": current_issue,
        "input_datasets": [
            {"file": item["file"], "dataset_id": item["dataset_id"], "issue": item["issue"]}
            for item in (previous_item, current_item)
        ],
        "counts": dict(sorted(counts.items())),
        "screened_event_count": len(results),
        "finding_count": len(findings),
        "model": MODEL_VERSION,
        "criterion": CRITERION,
        "assessment_geometry": geometry_source,
        "assumptions": [
            "Foreign FB transmitting/base stations are calculated; ML receiving land-mobile rows remain in trend counts.",
            "The true nearest point along the generalised GISCO Finland boundary/coastline (projection onto every "
            "boundary segment, not the nearest vertex) is screened.",
            "Co-frequency Finnish stations in the supplied workbook are screened as supplemental assessment points.",
            "A land-only path and rural 10 m receiver clutter are used without a terrain profile.",
            "Maximum available ERP and effective antenna height are used for conservative screening.",
            "No bandwidth conversion is applied because occupied bandwidth is not proven to be channel spacing with uniform spectral power.",
            "A threshold exceedance is an expert-review trigger, not proof of harmful interference.",
        ],
    }
    run_material = json.dumps(summary, sort_keys=True).encode()
    summary["run_id"] = hashlib.sha256(run_material).hexdigest()
    (output / "terrestrial_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
