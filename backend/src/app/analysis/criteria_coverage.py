"""Report which review cases have an applicable pfd criterion.

For every review case, each satellite frequency band is looked up against the
criteria table (currently RR Table 21-4, Finland / Region 1 rows only). Orbit is
taken from the notice type (G = geostationary, N = non-geostationary; anything
else is left unknown so both orbit kinds are returned). No pfd is calculated.
"""

import csv
import json
from pathlib import Path

from ..reference.pfd_criteria import criteria_for, load_criteria


METHOD = "pfd_criteria_coverage"
METHOD_VERSION = "1.0.0"
NOTICE_ORBIT = {"G": "gso", "N": "non_gso"}
RANGES_HZ = (
    (0, 30e6), (30e6, 300e6), (300e6, 1e9), (1e9, 3e9), (3e9, 10e9), (10e9, 20e9), (20e9, 40e9), (40e9, 1e12),
)


def _range_label(frequency_hz):
    for lower, upper in RANGES_HZ:
        if lower <= frequency_hz < upper:
            return f"{lower / 1e6:g}-{upper / 1e6:g} MHz"
    return "unknown"


def relevant_intervals(case):
    """Satellite frequencies that matter for this Finnish band, not the whole satellite band.

    Co-frequency: the intersection segments. Adjacent: each satellite band clipped to
    the protected band widened by one protected bandwidth on each side.
    """
    if case["matched_frequency_segments_hz"]:
        return [(item["frequency_min_hz"], item["frequency_max_hz"]) for item in case["matched_frequency_segments_hz"]]
    finnish = case["finnish_usage"]
    guard = int(finnish.get("bandwidth_hz") or 0)
    lower, upper = finnish["frequency_min_hz"] - guard, finnish["frequency_max_hz"] + guard
    intervals = []
    for band in case["space_frequency_bands"]:
        clipped = (max(lower, band["frequency_min_hz"]), min(upper, band["frequency_max_hz"]))
        if clipped[0] <= clipped[1]:
            intervals.append(clipped)
    return intervals


def case_coverage(case, document):
    orbit = NOTICE_ORBIT.get(case["space"].get("notice_type"))
    criterion_ids, partial = set(), False
    for lower, upper in relevant_intervals(case):
        for result in criteria_for(lower, upper, orbit, document=document):
            if result["status"] == "criterion":
                criterion_ids.add(result["criterion_id"])
                partial = partial or result["overlap"] == "partial"
    return {
        "case_id": case["case_id"],
        "orbit": orbit or "unknown",
        "coverage": "hard_limit" if criterion_ids else "no_criterion",
        "criterion_ids": sorted(criterion_ids),
        "any_partial_band_overlap": partial,
    }


def _read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def run(cases_path, output):
    cases_path, output = cases_path.resolve(), output.resolve()
    if not cases_path.is_file():
        raise ValueError(f"Review-case input does not exist: {cases_path}")
    document = load_criteria()
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "case_criteria_coverage.csv"
    summary_path = output / "criteria_coverage_summary.json"
    fields = (
        "case_id", "space_file", "notice_id", "administration", "notice_type", "orbit", "station_number",
        "protected_center_hz", "frequency_range", "frequency_relation", "coverage", "criterion_ids",
        "any_partial_band_overlap",
    )
    totals = {}
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for case in _read_jsonl(cases_path):
            result = case_coverage(case, document)
            space, finnish = case["space"], case["finnish_usage"]
            frequency_range = _range_label(finnish["center_hz"])
            writer.writerow({
                "case_id": case["case_id"], "space_file": space["file"], "notice_id": space["notice_id"],
                "administration": space["administration"], "notice_type": space["notice_type"],
                "orbit": result["orbit"], "station_number": finnish["station_number"],
                "protected_center_hz": finnish["center_hz"], "frequency_range": frequency_range,
                "frequency_relation": case["frequency_relation"]["relation"], "coverage": result["coverage"],
                "criterion_ids": "|".join(result["criterion_ids"]),
                "any_partial_band_overlap": result["any_partial_band_overlap"],
            })
            dataset = totals.setdefault(space["file"], {"dataset_kind": space["dataset_kind"], "ranges": {}})
            bucket = dataset["ranges"].setdefault(frequency_range, {
                "hard_limit": 0, "no_criterion": 0, "_notices_without": set(), "_criteria": {},
            })
            bucket[result["coverage"]] += 1
            if result["coverage"] == "no_criterion":
                bucket["_notices_without"].add(space["notice_id"])
            for criterion_id in result["criterion_ids"]:
                bucket["_criteria"][criterion_id] = bucket["_criteria"].get(criterion_id, 0) + 1
    datasets = []
    for file_name in sorted(totals):
        ranges = []
        for label, bucket in sorted(totals[file_name]["ranges"].items(), key=lambda item: float(item[0].split("-")[0])):
            ranges.append({
                "frequency_range": label, "cases_with_hard_limit": bucket["hard_limit"],
                "cases_without_criterion": bucket["no_criterion"],
                "notices_without_criterion": len(bucket.pop("_notices_without")),
                "cases_by_criterion": dict(sorted(bucket.pop("_criteria").items(), key=lambda item: -item[1])),
            })
        datasets.append({"file": file_name, "dataset_kind": totals[file_name]["dataset_kind"], "ranges": ranges})
    summary = {
        "schema_version": 1, "method": METHOD, "method_version": METHOD_VERSION, "status": "completed",
        "criteria_status": document["transcription"]["status"],
        "criteria_scope": document["scope"]["included"],
        "assumptions": [
            "Orbit from notice type: G = GSO, N = non-GSO, other = unknown (both orbit kinds considered).",
            "Only Table 21-4 bands applicable in Finland (ITU Region 1, Article 5 country footnotes checked) are used.",
            "Service and constellation conditions (HEO, satellite count, X/Y parameters) are not yet resolved per notice.",
            "Only the satellite frequencies that touch the Finnish band are looked up: the overlap for co-frequency cases, the satellite band clipped to the protected band +/- one protected bandwidth for adjacent cases.",
            "Grouping by frequency range uses the Finnish protected-band centre frequency.",
        ],
        "datasets": datasets,
        "outputs": {"csv": csv_path.name},
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
