import csv
import hashlib
import json
from pathlib import Path


METHOD = "frequency_overlap_case_consolidation"
METHOD_VERSION = "1.1.0"
INPUT_CLASSIFICATIONS = {"frequency_match_candidate", "frequency_overlap_candidate"}


def merge_closed_intervals(intervals):
    ordered = sorted((int(lower), int(upper)) for lower, upper in intervals)
    merged = []
    for lower, upper in ordered:
        if lower > upper:
            raise ValueError("Inverted interval")
        if not merged or lower > merged[-1][1]:
            merged.append([lower, upper])
        else:
            merged[-1][1] = max(merged[-1][1], upper)
    return [{"frequency_min_hz": lower, "frequency_max_hz": upper} for lower, upper in merged]


def _case_key(record):
    space, finnish = record["space"], record["finnish_usage"]
    return (
        space["dataset_id"], space.get("notice_id"), finnish["dataset_id"],
        finnish["source_row"], finnish["frequency_role"],
    )


def _stable_case_id(key):
    value = json.dumps([METHOD_VERSION, *key], separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def _new_case(record, key):
    space, finnish = record["space"], record["finnish_usage"]
    return {
        "schema_version": 1,
        "case_id": _stable_case_id(key),
        "classification": "frequency_overlap_review_case",
        "analysis_status": "screening_only_not_interference_finding",
        "space": {
            name: space.get(name) for name in (
                "dataset_id", "file", "dataset_kind", "issue", "notice_source_row", "notice_id",
                "administration", "notice_type", "provision", "notice_publication_issue",
                "publication_date", "action_code", "publication_part", "status_code",
            )
        },
        "finnish_usage": dict(finnish),
        "match_basis": "one_space_notice_to_one_finnish_station_band",
        "calculation_status": "not_started",
        "_satellites": {},
        "_frequency_rows": set(),
        "_frequency_bands": {},
        "_group_ids": set(),
        "_sequence_numbers": set(),
        "_beam_names": set(),
        "_overlap_intervals": [],
        "_adjacent": [],
        "_raw_match_count": 0,
    }


def _add_record(case, record):
    space, finnish = record["space"], record["finnish_usage"]
    if case["space"]["dataset_id"] != space["dataset_id"] or case["finnish_usage"]["source_row"] != finnish["source_row"]:
        raise ValueError("Case key mismatch")
    source_row = int(space["frequency_source_row"])
    if source_row in case["_frequency_rows"]:
        raise ValueError(f"Duplicate frequency source row in case: {source_row}")
    case["_frequency_rows"].add(source_row)
    for satellite in space.get("satellites", []):
        satellite_key = (satellite.get("source_table"), satellite.get("source_row"))
        case["_satellites"][satellite_key] = satellite
    if space.get("group_id") is not None:
        case["_group_ids"].add(space["group_id"])
    if space.get("sequence_number") is not None:
        case["_sequence_numbers"].add(space["sequence_number"])
    if space.get("beam_name"):
        case["_beam_names"].add(space["beam_name"])
    band_key = (
        space.get("center_hz"), space.get("bandwidth_hz"),
        space["frequency_min_hz"], space["frequency_max_hz"],
    )
    band = case["_frequency_bands"].setdefault(band_key, {
        "center_hz": space.get("center_hz"), "bandwidth_hz": space.get("bandwidth_hz"),
        "frequency_min_hz": space["frequency_min_hz"], "frequency_max_hz": space["frequency_max_hz"],
        "source_row_count": 0,
    })
    band["source_row_count"] += 1
    lower = max(space["frequency_min_hz"], finnish["frequency_min_hz"])
    upper = min(space["frequency_max_hz"], finnish["frequency_max_hz"])
    relation = (record.get("frequency_relation") or {}).get("relation", "co_frequency")
    if relation == "co_frequency":
        if lower > upper:
            raise ValueError("Co-frequency record does not contain a frequency intersection")
        case["_overlap_intervals"].append((lower, upper))
    elif relation == "adjacent":
        if lower <= upper:
            raise ValueError("Adjacent record unexpectedly intersects the protected band")
        side = "below" if space["frequency_max_hz"] < finnish["frequency_min_hz"] else "above"
        case["_adjacent"].append((lower - upper, side))
    else:
        raise ValueError(f"Unsupported frequency relation: {relation!r}")
    case["_raw_match_count"] += 1


def _finish_case(case):
    case["space"]["satellites"] = sorted(
        case.pop("_satellites").values(), key=lambda item: (item.get("source_table") or "", item.get("source_row") or 0)
    )
    frequency_rows = sorted(case.pop("_frequency_rows"))
    bands = sorted(
        case.pop("_frequency_bands").values(),
        key=lambda item: (item["frequency_min_hz"], item["frequency_max_hz"], item.get("center_hz") or -1),
    )
    segments = merge_closed_intervals(case.pop("_overlap_intervals"))
    adjacent = case.pop("_adjacent")
    finnish = case["finnish_usage"]
    protected_width = finnish["frequency_max_hz"] - finnish["frequency_min_hz"]
    covered = sum(item["frequency_max_hz"] - item["frequency_min_hz"] for item in segments)
    case["matched_frequency_segments_hz"] = segments
    case["frequency_relation"] = {
        "relation": "co_frequency" if segments else "adjacent",
        "overlap_hz": covered,
        "overlap_fraction_of_protected": (
            (1.0 if protected_width == 0 else round(covered / protected_width, 6)) if segments else 0.0
        ),
        "nearest_adjacent_separation_hz": min((gap for gap, _ in adjacent), default=None),
        "adjacent_sides": sorted({side for _, side in adjacent}),
        "co_frequency_rows": case["_raw_match_count"] - len(adjacent),
        "adjacent_rows": len(adjacent),
    }
    case["space_frequency_bands"] = bands
    case["evidence"] = {
        "raw_match_count": case.pop("_raw_match_count"),
        "frequency_source_table": "freq",
        "frequency_source_rows": frequency_rows,
        "frequency_source_row_count": len(frequency_rows),
        "group_ids": sorted(case.pop("_group_ids")),
        "sequence_numbers": sorted(case.pop("_sequence_numbers")),
        "beam_names": sorted(case.pop("_beam_names")),
    }
    return case


def consolidate(records):
    cases = {}
    for record in records:
        if record.get("classification") not in INPUT_CLASSIFICATIONS:
            raise ValueError("Unsupported input record classification")
        key = _case_key(record)
        case = cases.setdefault(key, _new_case(record, key))
        _add_record(case, record)
    return [_finish_case(cases[key]) for key in sorted(cases, key=lambda item: tuple("" if v is None else str(v) for v in item))]


def notice_rollups(cases):
    rollups = {}
    for case in cases:
        space, finnish, relation = case["space"], case["finnish_usage"], case["frequency_relation"]
        key = (space["dataset_id"], space.get("notice_id"))
        rollup = rollups.setdefault(key, {
            "schema_version": 1,
            "classification": "notice_frequency_match_rollup",
            "analysis_status": "screening_only_not_interference_finding",
            "space": {name: space.get(name) for name in (
                "dataset_id", "file", "dataset_kind", "issue", "notice_source_row", "notice_id",
                "administration", "notice_type", "provision", "notice_publication_issue",
                "publication_date", "action_code", "publication_part", "status_code",
            )},
            "satellite_names": set(),
            "case_ids": [],
            "stations": [],
            "_bands": [],
            "counts": {"co_frequency_cases": 0, "adjacent_cases": 0},
        })
        rollup["satellite_names"].update(
            str(item["satellite_name"]) for item in space.get("satellites", []) if item.get("satellite_name")
        )
        rollup["case_ids"].append(case["case_id"])
        rollup["counts"][relation["relation"] + "_cases"] += 1
        rollup["stations"].append({
            "case_id": case["case_id"], "station_number": finnish["station_number"],
            "station_source_row": finnish["source_row"], "frequency_role": finnish["frequency_role"],
            "center_hz": finnish["center_hz"], "bandwidth_hz": finnish["bandwidth_hz"],
            "longitude": finnish.get("longitude"), "latitude": finnish.get("latitude"),
            "relation": relation["relation"],
            "overlap_fraction_of_protected": relation["overlap_fraction_of_protected"],
            "nearest_adjacent_separation_hz": relation["nearest_adjacent_separation_hz"],
        })
        rollup["_bands"].extend(
            (band["frequency_min_hz"], band["frequency_max_hz"]) for band in case["space_frequency_bands"]
        )
    result = []
    for key in sorted(rollups, key=lambda item: tuple("" if v is None else str(v) for v in item)):
        rollup = rollups[key]
        rollup["matched_space_frequency_ranges_hz"] = merge_closed_intervals(rollup.pop("_bands"))
        rollup["satellite_names"] = sorted(rollup["satellite_names"])
        rollup["counts"]["review_cases"] = len(rollup["case_ids"])
        rollup["counts"]["distinct_stations"] = len({item["station_source_row"] for item in rollup["stations"]})
        rollup["stations"].sort(key=lambda item: (
            item["relation"] != "co_frequency", item["station_source_row"], item["frequency_role"],
        ))
        result.append(rollup)
    return result


def _read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def run(input_path, output):
    input_path, output = input_path.resolve(), output.resolve()
    if not input_path.is_file():
        raise ValueError(f"Frequency-match input does not exist: {input_path}")
    cases = consolidate(_read_jsonl(input_path))
    output.mkdir(parents=True, exist_ok=True)
    jsonl_path = output / "frequency_review_cases.jsonl"
    csv_path = output / "frequency_review_cases.csv"
    summary_path = output / "frequency_review_case_summary.json"
    fields = (
        "case_id", "space_file", "space_dataset_kind", "space_issue", "notice_id", "administration",
        "notice_type", "provision", "action_code", "publication_part", "status_code", "satellite_names",
        "station_number", "station_source_row", "protected_frequency_role", "protected_center_hz",
        "protected_bandwidth_hz", "frequency_relation", "overlap_hz", "overlap_fraction_of_protected",
        "nearest_adjacent_separation_hz", "adjacent_sides", "matched_frequency_segments_hz", "space_frequency_band_count",
        "frequency_source_row_count", "group_count", "beam_count", "calculation_status",
    )
    dataset_stats = {}
    raw_match_count = 0
    with jsonl_path.open("w", encoding="utf-8") as json_stream, csv_path.open("w", encoding="utf-8", newline="") as csv_stream:
        writer = csv.DictWriter(csv_stream, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            json_stream.write(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n")
            space, finnish, evidence = case["space"], case["finnish_usage"], case["evidence"]
            raw_match_count += evidence["raw_match_count"]
            stats = dataset_stats.setdefault(space["dataset_id"], {
                "dataset_id": space["dataset_id"], "file": space["file"], "issue": space["issue"],
                "dataset_kind": space["dataset_kind"], "review_cases": 0, "raw_match_candidates": 0,
                "notice_ids": set(), "station_bands": set(), "cases_by_relation": {},
            })
            stats["review_cases"] += 1
            kind = case["frequency_relation"]["relation"]
            stats["cases_by_relation"][kind] = stats["cases_by_relation"].get(kind, 0) + 1
            stats["raw_match_candidates"] += evidence["raw_match_count"]
            stats["notice_ids"].add(space["notice_id"])
            stats["station_bands"].add((finnish["source_row"], finnish["frequency_role"]))
            writer.writerow({
                "case_id": case["case_id"], "space_file": space["file"],
                "space_dataset_kind": space["dataset_kind"], "space_issue": space["issue"],
                "notice_id": space["notice_id"], "administration": space["administration"],
                "notice_type": space["notice_type"], "provision": space["provision"],
                "action_code": space["action_code"], "publication_part": space["publication_part"],
                "status_code": space["status_code"],
                "satellite_names": "|".join(sorted({str(item["satellite_name"]) for item in space["satellites"] if item.get("satellite_name")})),
                "station_number": finnish["station_number"], "station_source_row": finnish["source_row"],
                "protected_frequency_role": finnish["frequency_role"], "protected_center_hz": finnish["center_hz"],
                "protected_bandwidth_hz": finnish["bandwidth_hz"],
                "frequency_relation": case["frequency_relation"]["relation"],
                "overlap_hz": case["frequency_relation"]["overlap_hz"],
                "overlap_fraction_of_protected": case["frequency_relation"]["overlap_fraction_of_protected"],
                "nearest_adjacent_separation_hz": case["frequency_relation"]["nearest_adjacent_separation_hz"],
                "adjacent_sides": "|".join(case["frequency_relation"]["adjacent_sides"]),
                "matched_frequency_segments_hz": "|".join(
                    f'{item["frequency_min_hz"]}-{item["frequency_max_hz"]}' for item in case["matched_frequency_segments_hz"]
                ),
                "space_frequency_band_count": len(case["space_frequency_bands"]),
                "frequency_source_row_count": evidence["frequency_source_row_count"],
                "group_count": len(evidence["group_ids"]), "beam_count": len(evidence["beam_names"]),
                "calculation_status": case["calculation_status"],
            })
    rollups = notice_rollups(cases)
    rollup_jsonl = output / "notice_rollups.jsonl"
    rollup_csv = output / "notice_rollups.csv"
    rollup_fields = (
        "space_file", "space_dataset_kind", "space_issue", "notice_id", "administration", "notice_type",
        "provision", "action_code", "status_code", "satellite_names", "review_cases", "co_frequency_cases",
        "adjacent_cases", "distinct_stations", "matched_space_frequency_ranges_hz",
    )
    with rollup_jsonl.open("w", encoding="utf-8") as json_stream, \
            rollup_csv.open("w", encoding="utf-8", newline="") as csv_stream:
        writer = csv.DictWriter(csv_stream, fieldnames=rollup_fields)
        writer.writeheader()
        for rollup in rollups:
            json_stream.write(json.dumps(rollup, ensure_ascii=False, separators=(",", ":")) + "\n")
            space, counts = rollup["space"], rollup["counts"]
            writer.writerow({
                "space_file": space["file"], "space_dataset_kind": space["dataset_kind"],
                "space_issue": space["issue"], "notice_id": space["notice_id"],
                "administration": space["administration"], "notice_type": space["notice_type"],
                "provision": space["provision"], "action_code": space["action_code"],
                "status_code": space["status_code"], "satellite_names": "|".join(rollup["satellite_names"]),
                "review_cases": counts["review_cases"], "co_frequency_cases": counts["co_frequency_cases"],
                "adjacent_cases": counts["adjacent_cases"], "distinct_stations": counts["distinct_stations"],
                "matched_space_frequency_ranges_hz": "|".join(
                    f'{item["frequency_min_hz"]}-{item["frequency_max_hz"]}'
                    for item in rollup["matched_space_frequency_ranges_hz"]
                ),
            })
    datasets = []
    for stats in sorted(dataset_stats.values(), key=lambda item: item["file"]):
        stats["distinct_notices"] = len(stats.pop("notice_ids"))
        stats["matched_station_bands"] = len(stats.pop("station_bands"))
        datasets.append(stats)
    summary = {
        "schema_version": 1, "method": METHOD, "method_version": METHOD_VERSION,
        "status": "completed", "scope": "frequency_overlap_case_consolidation_only",
        "source_match_candidates_modified": False,
        "grouping_key": ["space_dataset_id", "notice_id", "finnish_dataset_id", "station_source_row", "frequency_role"],
        "review_cases": len(cases), "raw_match_candidates": raw_match_count,
        "notice_rollups": len(rollups),
        "datasets": datasets,
        "outputs": {
            "jsonl": jsonl_path.name, "csv": csv_path.name,
            "notice_rollups_jsonl": rollup_jsonl.name, "notice_rollups_csv": rollup_csv.name,
        },
        "next_stage": "deterministic technical and regulatory calculations",
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
