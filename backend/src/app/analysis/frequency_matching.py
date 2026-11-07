"""Match satellite downlink bands to Finnish protected-frequency bands.

Two relations are screened: co-frequency (closed intervals intersect) and adjacent
(the gap between the bands is at most ``adjacent_channels`` protected bandwidths).
This module performs screening only. It does not calculate PFD, field strength,
propagation, regulatory limits, margins, or interference risk.
"""

from bisect import bisect_right
import csv
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
from pathlib import Path


METHOD = "satellite_finnish_frequency_overlap"
METHOD_VERSION = "1.1.0"
DEFAULT_ADJACENT_CHANNELS = 1
WORKBOOK_TABLE = "Frequencies of interest"


def _read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _prepared_path(prepared, relative):
    path = (prepared / relative).resolve()
    if not path.is_relative_to(prepared.resolve()):
        raise ValueError("Prepared output path escapes its directory")
    return path


def _whole_hz(value, unit_factor=1):
    if value is None or str(value).strip() == "":
        return None
    try:
        result = Decimal(str(value)) * unit_factor
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite() or result < 0:
        return None
    return result


def _outward_band(center_hz, bandwidth_hz):
    center = Decimal(center_hz)
    width = Decimal(bandwidth_hz or 0)
    lower = (center - width / 2).to_integral_value(rounding=ROUND_FLOOR)
    upper = (center + width / 2).to_integral_value(rounding=ROUND_CEILING)
    return int(lower), int(upper)


def protected_bands(station):
    """Return deduplicated RX/TX bands that represent Finnish protected use."""
    width = station.get("effective_bandwidth_hz")
    if width is None:
        channel = station.get("channel_bandwidth_hz")
        transmission = station.get("transmission_bandwidth_hz")
        available = [value for value in (channel, transmission) if value is not None]
        width = min(available, default=0)
    frequencies = {}
    for role, key in (("rx", "rx_frequency_hz"), ("tx", "tx_frequency_hz")):
        center = station.get(key)
        if center is not None:
            frequencies.setdefault(int(center), []).append(role)
    bands = []
    for center, roles in frequencies.items():
        lower, upper = _outward_band(center, width)
        bands.append({
            "frequency_role": "_".join(roles),
            "center_hz": center,
            "bandwidth_hz": int(width),
            "frequency_min_hz": lower,
            "frequency_max_hz": upper,
        })
    return bands


def satellite_band(frequency):
    """Normalize an ITU freq row to a closed whole-Hz interval."""
    lower = _whole_hz(frequency.get("freq_min"), Decimal(1000000))
    upper = _whole_hz(frequency.get("freq_max"), Decimal(1000000))
    center = _whole_hz(frequency.get("freq_mhz"), Decimal(1000000))
    bandwidth = _whole_hz(frequency.get("bdwdth"), Decimal(1000))
    if lower is None or upper is None:
        if center is None:
            return None
        lower_int, upper_int = _outward_band(center, bandwidth or 0)
    else:
        lower_int = int(lower.to_integral_value(rounding=ROUND_FLOOR))
        upper_int = int(upper.to_integral_value(rounding=ROUND_CEILING))
    if lower_int > upper_int:
        return None
    return {
        "center_hz": None if center is None else int(center),
        "bandwidth_hz": None if bandwidth is None else int(bandwidth),
        "frequency_min_hz": lower_int,
        "frequency_max_hz": upper_int,
    }


def search_window(band, adjacent_channels=0):
    """Return the protected band widened by N protected bandwidths on each side."""
    guard = int(band.get("bandwidth_hz") or 0) * int(adjacent_channels)
    return max(0, band["frequency_min_hz"] - guard), band["frequency_max_hz"] + guard, guard


def frequency_relation(satellite, protected):
    """Describe how a satellite band relates to a protected band (whole Hz)."""
    lower = max(satellite["frequency_min_hz"], protected["frequency_min_hz"])
    upper = min(satellite["frequency_max_hz"], protected["frequency_max_hz"])
    protected_width = protected["frequency_max_hz"] - protected["frequency_min_hz"]
    if upper >= lower:
        overlap = upper - lower
        return {
            "relation": "co_frequency", "separation_hz": 0, "overlap_hz": overlap,
            "overlap_fraction_of_protected": 1.0 if protected_width == 0 else round(overlap / protected_width, 6),
            "satellite_side": "covers" if (
                satellite["frequency_min_hz"] <= protected["frequency_min_hz"]
                and satellite["frequency_max_hz"] >= protected["frequency_max_hz"]
            ) else "partial",
        }
    side = "below" if satellite["frequency_max_hz"] < protected["frequency_min_hz"] else "above"
    return {
        "relation": "adjacent", "separation_hz": lower - upper, "overlap_hz": 0,
        "overlap_fraction_of_protected": 0.0, "satellite_side": side,
    }


def match_intervals(satellite_rows, finnish_bands, adjacent_channels=0):
    """Yield (satellite, protected, relation) for co-frequency and adjacent pairs."""
    windows = []
    for band in finnish_bands:
        lower, upper, guard = search_window(band, adjacent_channels)
        windows.append((lower, upper, guard, band))
    windows.sort(key=lambda item: (item[0], item[1]))
    starts = [item[0] for item in windows]
    for satellite in satellite_rows:
        stop = bisect_right(starts, satellite["frequency_max_hz"])
        for lower, upper, guard, protected in windows[:stop]:
            if upper >= satellite["frequency_min_hz"]:
                relation = frequency_relation(satellite, protected)
                relation["adjacent_guard_hz"] = guard
                yield satellite, protected, relation


def _dataset_kind(file_name):
    name = Path(file_name).name.lower()
    if name.startswith("ific"):
        return "space_ific_evaluation"
    if name.startswith("sps_all"):
        return "ap30_30a_reference_snapshot"
    if name.startswith("30b_"):
        return "ap30b_reference_snapshot"
    return "space_reference"


def _load_table(prepared, dataset, table_name):
    metadata = dataset["extraction"]["tables"][table_name]
    directory = _prepared_path(prepared, dataset["output_directory"])
    return list(_read_jsonl(_prepared_path(directory, metadata["output"])))


def _stable_match_id(space_dataset_id, frequency_source_row, station_dataset_id, station_source_row, role):
    value = f"{METHOD_VERSION}|{space_dataset_id}|{frequency_source_row}|{station_dataset_id}|{station_source_row}|{role}"
    return hashlib.sha256(value.encode()).hexdigest()


def run(prepared, output, space_files=None, adjacent_channels=DEFAULT_ADJACENT_CHANNELS):
    if adjacent_channels < 0:
        raise ValueError("adjacent_channels must be non-negative")
    prepared, output = prepared.resolve(), output.resolve()
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete") or manifest.get("errors"):
        raise ValueError("Preparation is incomplete; resolve its errors before matching")
    workbook = next((item for item in manifest["datasets"] if item.get("is_synthetic") and item.get("status") == "extracted"), None)
    if workbook is None:
        raise ValueError("No extracted Finnish frequency workbook found")
    selected_names = set(space_files or ())
    space_datasets = [
        item for item in manifest["datasets"]
        if item.get("status") == "extracted" and item["file"].lower().endswith(".mdb")
        and not Path(item["file"]).name.lower().startswith("brific")
        and (not selected_names or Path(item["file"]).name in selected_names)
    ]
    if not space_datasets:
        raise ValueError("No extracted space MDB datasets matched")
    if selected_names:
        found = {Path(item["file"]).name for item in space_datasets}
        if missing := selected_names - found:
            raise ValueError(f"Requested space files were not prepared: {sorted(missing)}")

    workbook_directory = _prepared_path(prepared, workbook["output_directory"])
    station_file = _prepared_path(workbook_directory, workbook["extraction"]["output"])
    finnish_bands = []
    for station_record in _read_jsonl(station_file):
        for band in protected_bands(station_record):
            finnish_bands.append({**band, "station": station_record})

    output.mkdir(parents=True, exist_ok=True)
    jsonl_path = output / "frequency_match_candidates.jsonl"
    csv_path = output / "frequency_match_candidates.csv"
    summary_path = output / "frequency_match_summary.json"
    dataset_summaries = []
    match_count = 0
    matched_stations, matched_notices = set(), set()
    relation_counts = {}
    csv_fields = (
        "match_id", "space_file", "space_dataset_kind", "space_issue", "frequency_source_row",
        "notice_id", "administration", "notice_publication_issue", "frequency_publication_issue",
        "notice_type", "provision", "action_code", "publication_part", "status_code",
        "satellite_names", "group_id", "sequence_number",
        "satellite_frequency_min_hz", "satellite_frequency_max_hz", "frequency_relation",
        "separation_hz", "overlap_hz", "overlap_fraction_of_protected", "satellite_side", "station_number",
        "station_source_row", "protected_frequency_role", "protected_center_hz",
        "protected_bandwidth_hz", "protected_frequency_min_hz", "protected_frequency_max_hz",
        "longitude", "latitude", "station_quality_flags",
    )
    with jsonl_path.open("w", encoding="utf-8") as json_stream, csv_path.open("w", encoding="utf-8", newline="") as csv_stream:
        writer = csv.DictWriter(csv_stream, fieldnames=csv_fields)
        writer.writeheader()
        for dataset in sorted(space_datasets, key=lambda item: item["file"]):
            notices = {row["raw"].get("ntc_id"): row for row in _load_table(prepared, dataset, "notice")}
            satellites = {}
            for table_name in ("geo", "non_geo"):
                for row in _load_table(prepared, dataset, table_name):
                    satellites.setdefault(row["raw"].get("ntc_id"), []).append({
                        "source_table": table_name,
                        "source_row": row["source_row"],
                        "satellite_name": row["raw"].get("sat_name"),
                        "nominal_longitude_deg": row["raw"].get("long_nom"),
                    })
            downlinks, rejected = [], 0
            for row in _load_table(prepared, dataset, "freq"):
                raw = row["raw"]
                if raw.get("emi_rcp") != "E":
                    continue
                band = satellite_band(raw)
                if band is None:
                    rejected += 1
                    continue
                downlinks.append({**band, "source": row})
            dataset_matches, dataset_relations = 0, {}
            for satellite, protected, relation in match_intervals(downlinks, finnish_bands, adjacent_channels):
                frequency = satellite["source"]
                raw = frequency["raw"]
                station = protected["station"]
                notice = notices.get(raw.get("ntc_id"))
                notice_raw = notice["raw"] if notice else {}
                satellite_records = satellites.get(raw.get("ntc_id"), [])
                match_id = _stable_match_id(
                    dataset["dataset_id"], frequency["source_row"], workbook["dataset_id"],
                    station["source_row"], protected["frequency_role"],
                )
                record = {
                    "schema_version": 1,
                    "match_id": match_id,
                    "classification": "frequency_match_candidate",
                    "frequency_relation": relation,
                    "analysis_status": "screening_only_not_interference_finding",
                    "space": {
                        "dataset_id": dataset["dataset_id"], "file": dataset["file"],
                        "dataset_kind": _dataset_kind(dataset["file"]), "issue": dataset.get("issue"),
                        "frequency_source_table": "freq", "frequency_source_row": frequency["source_row"],
                        "notice_source_row": None if notice is None else notice["source_row"],
                        "notice_id": raw.get("ntc_id"), "administration": notice_raw.get("adm"),
                        "notice_type": notice_raw.get("ntc_type"), "provision": notice_raw.get("prov"),
                        "notice_publication_issue": notice_raw.get("wic_no"),
                        "frequency_publication_issue": raw.get("wic_no"),
                        "publication_date": notice_raw.get("d_wic"), "action_code": notice_raw.get("act_code"),
                        "publication_part": notice_raw.get("wic_part"), "status_code": notice_raw.get("st_cur"),
                        "group_id": raw.get("grp_id"), "sequence_number": raw.get("seq_no"),
                        "emission_reception_code": raw.get("emi_rcp"), "beam_name": raw.get("beam_name"),
                        "center_hz": satellite["center_hz"], "bandwidth_hz": satellite["bandwidth_hz"],
                        "frequency_min_hz": satellite["frequency_min_hz"],
                        "frequency_max_hz": satellite["frequency_max_hz"],
                        "satellites": satellite_records,
                    },
                    "finnish_usage": {
                        "dataset_id": workbook["dataset_id"], "file": workbook["file"],
                        "source_table": WORKBOOK_TABLE, "source_row": station["source_row"],
                        "station_number": station["station_number"],
                        "frequency_role": protected["frequency_role"], "center_hz": protected["center_hz"],
                        "bandwidth_hz": protected["bandwidth_hz"],
                        "bandwidth_source": station.get("effective_bandwidth_source"),
                        "frequency_min_hz": protected["frequency_min_hz"],
                        "frequency_max_hz": protected["frequency_max_hz"],
                        "longitude": station.get("longitude"), "latitude": station.get("latitude"),
                        "quality_flags": station.get("quality_flags", []),
                    },
                    "match_basis": (
                        "closed_frequency_intervals_intersect" if relation["relation"] == "co_frequency"
                        else f"gap_within_{adjacent_channels}_protected_bandwidths"
                    ),
                    "calculation_status": "not_started",
                }
                json_stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                writer.writerow({
                    "match_id": match_id, "space_file": dataset["file"],
                    "space_dataset_kind": _dataset_kind(dataset["file"]), "space_issue": dataset.get("issue"),
                    "frequency_source_row": frequency["source_row"], "notice_id": raw.get("ntc_id"),
                    "administration": notice_raw.get("adm"),
                    "notice_publication_issue": notice_raw.get("wic_no"),
                    "frequency_publication_issue": raw.get("wic_no"),
                    "notice_type": notice_raw.get("ntc_type"), "provision": notice_raw.get("prov"),
                    "action_code": notice_raw.get("act_code"), "publication_part": notice_raw.get("wic_part"),
                    "status_code": notice_raw.get("st_cur"),
                    "satellite_names": "|".join(sorted({str(item["satellite_name"]) for item in satellite_records if item["satellite_name"]})),
                    "group_id": raw.get("grp_id"), "sequence_number": raw.get("seq_no"),
                    "satellite_frequency_min_hz": satellite["frequency_min_hz"],
                    "satellite_frequency_max_hz": satellite["frequency_max_hz"],
                    "frequency_relation": relation["relation"], "separation_hz": relation["separation_hz"],
                    "overlap_hz": relation["overlap_hz"],
                    "overlap_fraction_of_protected": relation["overlap_fraction_of_protected"],
                    "satellite_side": relation["satellite_side"],
                    "station_number": station["station_number"], "station_source_row": station["source_row"],
                    "protected_frequency_role": protected["frequency_role"],
                    "protected_center_hz": protected["center_hz"], "protected_bandwidth_hz": protected["bandwidth_hz"],
                    "protected_frequency_min_hz": protected["frequency_min_hz"],
                    "protected_frequency_max_hz": protected["frequency_max_hz"],
                    "longitude": station.get("longitude"), "latitude": station.get("latitude"),
                    "station_quality_flags": "|".join(station.get("quality_flags", [])),
                })
                match_count += 1
                dataset_matches += 1
                dataset_relations[relation["relation"]] = dataset_relations.get(relation["relation"], 0) + 1
                relation_counts[relation["relation"]] = relation_counts.get(relation["relation"], 0) + 1
                matched_stations.add((station["source_row"], protected["frequency_role"]))
                matched_notices.add((dataset["dataset_id"], raw.get("ntc_id")))
            dataset_summaries.append({
                "dataset_id": dataset["dataset_id"], "file": dataset["file"], "issue": dataset.get("issue"),
                "dataset_kind": _dataset_kind(dataset["file"]), "downlink_frequency_records": len(downlinks),
                "rejected_frequency_records": rejected, "frequency_match_candidates": dataset_matches,
                "candidates_by_relation": dict(sorted(dataset_relations.items())),
            })
    summary = {
        "schema_version": 1, "method": METHOD, "method_version": METHOD_VERSION,
        "status": "completed", "scope": "frequency_overlap_screening_only",
        "source_data_modified": False,
        "assumptions": [
            "Only satellite records with emi_rcp=E are treated as space-to-Earth emissions.",
            "Co-frequency: closed whole-Hz intervals intersect (touching edges count, overlap_hz=0).",
            f"Adjacent: no intersection, but the gap is <= {adjacent_channels} x the protected bandwidth "
            "(brief: 'same or adjacent frequency range'; Traficom: concerns may arise near the frequency).",
            "Both Finnish RX and TX frequencies are protected; identical RX/TX values are deduplicated.",
            "The smaller of channel bandwidth and transmission bandwidth is used when both exist.",
            "Satellite beam direction is not filtered; worst-case pointing is retained for later analysis.",
            "No notice status, action, or publication-history filter is applied at this screening stage.",
            "Repeated source frequency rows are preserved rather than deduplicated.",
            "An overlap candidate is not evidence of harmful interference or a regulatory exceedance.",
        ],
        "finnish_station_records": workbook["extraction"]["records"],
        "finnish_protected_bands": len(finnish_bands),
        "matched_station_bands": len(matched_stations), "matched_notices": len(matched_notices),
        "adjacent_channels": adjacent_channels,
        "frequency_match_candidates": match_count,
        "candidates_by_relation": dict(sorted(relation_counts.items())), "datasets": dataset_summaries,
        "outputs": {"jsonl": jsonl_path.name, "csv": csv_path.name},
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
