"""Regulatory classification of consolidated frequency-overlap cases."""

import csv
import json
from pathlib import Path


METHOD = "space_ific_case_classification"
METHOD_VERSION = "1.0.0"
ITU_PREFACE_URL = "https://www.itu.int/en/ITU-R/space/Preface/preface_e.pdf"

NOTICE_OBJECTS = {
    "G": "geostationary_satellite_network",
    "N": "non_geostationary_satellite_network",
    "S": "specific_earth_station",
    "T": "typical_earth_station",
    "R": "radio_astronomy_station",
}

PUBLICATION_FAMILIES = {
    "9.1/IA": "advance_publication_api_a",
    "9.6": "coordination_request_cr_c",
    "11.2": "article_11_notification",
    "RS49": "resolution_49_due_diligence",
}

ACTIONS = {"A": "addition", "M": "modification", "S": "suppression"}

PUBLICATION_STAGES = {
    "1": "part_i_received_notification",
    "2": "part_ii_recorded_in_master_register",
    "3": "part_iii_returned_to_administration",
}


def classify_case(case):
    """Return a classified copy without dropping or modifying evidence."""
    result = dict(case)
    space = case["space"]
    code_values = {
        "notice_type": space.get("notice_type"),
        "provision": space.get("provision"),
        "action_code": space.get("action_code"),
        "publication_part": space.get("publication_part"),
        "status_code": space.get("status_code"),
    }
    dataset_role = "evaluation_issue" if space.get("dataset_kind") == "space_ific_evaluation" else "reference_snapshot"
    notice_object = NOTICE_OBJECTS.get(space.get("notice_type"), "unknown")
    publication_family = PUBLICATION_FAMILIES.get(space.get("provision"), "unknown")
    action = ACTIONS.get(space.get("action_code"), "unknown")
    part = None if space.get("publication_part") is None else str(space.get("publication_part"))
    if part in PUBLICATION_STAGES:
        publication_stage = PUBLICATION_STAGES[part]
    elif part is None and publication_family in {
        "advance_publication_api_a", "coordination_request_cr_c", "resolution_49_due_diligence"
    }:
        publication_stage = "special_section"
    else:
        publication_stage = "unknown"

    unknown_codes = []
    if notice_object == "unknown":
        unknown_codes.append("notice_type")
    if publication_family == "unknown":
        unknown_codes.append("provision")
    if action == "unknown":
        unknown_codes.append("action_code")
    if publication_stage == "unknown":
        unknown_codes.append("publication_part")

    reasons = []
    if dataset_role == "reference_snapshot":
        disposition = "reference_context"
        reasons.append("AP30/30A and AP30B snapshots provide plan context and are not evaluated IFIC notices.")
    elif unknown_codes:
        disposition = "needs_information"
        reasons.append("One or more public regulatory codes could not be mapped without guessing.")
    elif publication_stage == "part_iii_returned_to_administration":
        disposition = "returned_review_only"
        reasons.append("Part III-S assignments were returned to the notifying administration after examination.")
    elif publication_family == "resolution_49_due_diligence":
        disposition = "supporting_due_diligence_context"
        reasons.append("Resolution 49 is due-diligence publication context rather than a primary API/A or CR/C screening family.")
    elif notice_object in {"specific_earth_station", "typical_earth_station", "radio_astronomy_station"}:
        disposition = "eligible_with_specialist_review"
        reasons.append("The record is not a GSO/NGSO satellite-network notice and needs specialist confirmation before calculations.")
    else:
        disposition = "eligible_for_later_calculation"
        reasons.append(f"The IFIC {space.get('issue')} case is a mapped satellite-network publication and was not returned in Part III-S.")

    result["regulatory_classification"] = {
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "dataset_role": dataset_role,
        "notice_object": notice_object,
        "publication_family": publication_family,
        "publication_stage": publication_stage,
        "action": action,
        "disposition": disposition,
        "unknown_public_codes": unknown_codes,
        "internal_status_code": space.get("status_code"),
        "internal_status_interpreted": False,
        "reasons": reasons,
        "source": {"title": "ITU BR IFIC (Space Services) Preface", "edition": "May 2026", "url": ITU_PREFACE_URL},
        "raw_codes": code_values,
    }
    return result


def _read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def run(input_path, output):
    input_path, output = input_path.resolve(), output.resolve()
    if not input_path.is_file():
        raise ValueError(f"Review-case input does not exist: {input_path}")
    output.mkdir(parents=True, exist_ok=True)
    jsonl_path = output / "classified_frequency_cases.jsonl"
    csv_path = output / "classified_frequency_cases.csv"
    queue_path = output / "future_calculation_queue.jsonl"
    summary_path = output / "classification_summary.json"
    fields = (
        "case_id", "space_file", "space_issue", "notice_id", "administration", "satellite_names",
        "station_number", "station_source_row", "protected_frequency_role", "dataset_role", "notice_object",
        "publication_family", "publication_stage", "action", "disposition", "internal_status_code",
        "internal_status_interpreted", "raw_match_count", "calculation_status",
    )
    totals = {
        "dataset_role": {}, "notice_object": {}, "publication_family": {}, "publication_stage": {},
        "action": {}, "disposition": {},
    }
    dataset_stats = {}
    case_count = queue_count = unknown_count = 0
    seen_ids = set()
    with (
        jsonl_path.open("w", encoding="utf-8") as json_stream,
        csv_path.open("w", encoding="utf-8", newline="") as csv_stream,
        queue_path.open("w", encoding="utf-8") as queue_stream,
    ):
        writer = csv.DictWriter(csv_stream, fieldnames=fields)
        writer.writeheader()
        for case in _read_jsonl(input_path):
            classified = classify_case(case)
            case_id = classified["case_id"]
            if case_id in seen_ids:
                raise ValueError(f"Duplicate case id: {case_id}")
            seen_ids.add(case_id)
            classification = classified["regulatory_classification"]
            json_stream.write(json.dumps(classified, ensure_ascii=False, separators=(",", ":")) + "\n")
            case_count += 1
            if classification["unknown_public_codes"]:
                unknown_count += 1
            if classification["disposition"] in {"eligible_for_later_calculation", "eligible_with_specialist_review"}:
                queue_stream.write(json.dumps(classified, ensure_ascii=False, separators=(",", ":")) + "\n")
                queue_count += 1
            for name in totals:
                value = classification[name]
                totals[name][value] = totals[name].get(value, 0) + 1
            space, finnish = classified["space"], classified["finnish_usage"]
            stats = dataset_stats.setdefault(space["dataset_id"], {
                "dataset_id": space["dataset_id"], "file": space["file"], "issue": space["issue"],
                "dataset_role": classification["dataset_role"], "cases": 0, "future_calculation_queue": 0,
            })
            stats["cases"] += 1
            if classification["disposition"] in {"eligible_for_later_calculation", "eligible_with_specialist_review"}:
                stats["future_calculation_queue"] += 1
            writer.writerow({
                "case_id": case_id, "space_file": space["file"], "space_issue": space["issue"],
                "notice_id": space["notice_id"], "administration": space["administration"],
                "satellite_names": "|".join(sorted({str(item["satellite_name"]) for item in space["satellites"] if item.get("satellite_name")})),
                "station_number": finnish["station_number"], "station_source_row": finnish["source_row"],
                "protected_frequency_role": finnish["frequency_role"],
                "dataset_role": classification["dataset_role"], "notice_object": classification["notice_object"],
                "publication_family": classification["publication_family"],
                "publication_stage": classification["publication_stage"], "action": classification["action"],
                "disposition": classification["disposition"],
                "internal_status_code": classification["internal_status_code"],
                "internal_status_interpreted": classification["internal_status_interpreted"],
                "raw_match_count": classified["evidence"]["raw_match_count"],
                "calculation_status": classified["calculation_status"],
            })
    summary = {
        "schema_version": 1, "method": METHOD, "method_version": METHOD_VERSION, "status": "completed",
        "scope": "regulatory_classification_without_technical_calculation", "input_cases": case_count,
        "classified_cases": case_count, "cases_with_unknown_public_codes": unknown_count,
        "future_calculation_queue": queue_count,
        "internal_status_policy": "Preserved but not interpreted because the ITU Preface marks st_cur as BR internal use.",
        "classification_source": {"title": "ITU BR IFIC (Space Services) Preface", "edition": "May 2026", "url": ITU_PREFACE_URL},
        "counts": totals, "datasets": sorted(dataset_stats.values(), key=lambda item: item["file"]),
        "outputs": {"jsonl": jsonl_path.name, "csv": csv_path.name, "future_calculation_queue": queue_path.name},
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
