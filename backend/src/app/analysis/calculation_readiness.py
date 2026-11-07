"""Assemble and validate inputs for later PFD calculations without calculating PFD."""

import csv
import hashlib
import json
from pathlib import Path


METHOD = "pfd_input_readiness"
METHOD_VERSION = "1.0.0"
ITU_PREFACE_URL = "https://www.itu.int/en/ITU-R/space/Preface/preface_e.pdf"


def _read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Prepared output path escapes its directory")
    return path


def _load_table(prepared, dataset, table_name):
    metadata = dataset["extraction"]["tables"][table_name]
    folder = _safe_path(prepared, dataset["output_directory"])
    return list(_read_jsonl(_safe_path(folder, metadata["output"])))


def _profile_id(dataset_id, kind, source_id):
    return hashlib.sha256(f"{METHOD_VERSION}|{dataset_id}|{kind}|{source_id}".encode()).hexdigest()


def build_notice_profile(dataset_id, notice_id, notice_object, geo_rows, non_geo_rows, orbit_rows):
    geo = [row for row in geo_rows if row["raw"].get("ntc_id") == notice_id]
    non_geo = [row for row in non_geo_rows if row["raw"].get("ntc_id") == notice_id]
    orbits = [row for row in orbit_rows if row["raw"].get("ntc_id") == notice_id]
    missing = []
    if notice_object == "geostationary_satellite_network":
        if not any(row["raw"].get("long_nom") is not None for row in geo):
            missing.append("gso_nominal_longitude")
    elif notice_object == "non_geostationary_satellite_network":
        if not non_geo:
            missing.append("non_gso_constellation_record")
        has_altitude = any(
            row["raw"].get("perig_km") is not None or row["raw"].get("op_ht_km") is not None
            or row["raw"].get("perig_dist") is not None for row in orbits
        )
        if not orbits or not has_altitude:
            missing.append("non_gso_orbit_altitude")
    else:
        missing.append("specialist_orbit_interpretation")
    return {
        "schema_version": 1,
        "notice_profile_id": _profile_id(dataset_id, "notice", notice_id),
        "dataset_id": dataset_id,
        "notice_id": notice_id,
        "notice_object": notice_object,
        "geo_records": [{"source_row": row["source_row"], **row["raw"]} for row in geo],
        "non_geo_records": [{"source_row": row["source_row"], **row["raw"]} for row in non_geo],
        "orbit_records": [{"source_row": row["source_row"], **row["raw"]} for row in orbits],
        "missing_inputs": missing,
        "orbit_context_ready": not missing,
    }


def build_frequency_profile(dataset_id, frequency_row, groups, emissions_by_group, carrier_links, beams,
                            station_classes=None):
    raw = frequency_row["raw"]
    group_id, sequence_number = raw.get("grp_id"), raw.get("seq_no")
    group = groups.get(group_id)
    group_raw = {} if group is None else group["raw"]
    exact_emission_sequences = carrier_links.get((group_id, sequence_number), [])
    all_emissions = emissions_by_group.get(group_id, [])
    if exact_emission_sequences:
        selected = [row for row in all_emissions if row["raw"].get("seq_no") in exact_emission_sequences]
        emission_linkage = "exact_via_carrier_fr"
    elif all_emissions:
        selected = all_emissions
        emission_linkage = "group_level_worst_case"
    else:
        selected = []
        emission_linkage = "missing"
    beam_rows = beams.get((raw.get("ntc_id"), raw.get("emi_rcp"), raw.get("beam_name")), [])
    power_available = any(
        row["raw"].get("pep_max") is not None or row["raw"].get("pwr_ds_max") is not None for row in selected
    )
    gain_available = any(row["raw"].get("gain") is not None for row in beam_rows)
    missing = []
    if group is None:
        missing.append("group_record")
    if not selected:
        missing.append("emission_record")
    elif not power_available:
        missing.append("emission_power")
    if not beam_rows:
        missing.append("satellite_beam_record")
    elif not gain_available:
        missing.append("satellite_beam_gain")
    assumptions = ["worst_case_satellite_beam_pointing"]
    if emission_linkage == "group_level_worst_case":
        assumptions.append("consider_all_group_emissions_when_carrier_link_is_absent")
    return {
        "schema_version": 1,
        "frequency_profile_id": _profile_id(dataset_id, "frequency", frequency_row["source_row"]),
        "dataset_id": dataset_id,
        "frequency_source_table": "freq",
        "frequency_source_row": frequency_row["source_row"],
        "notice_id": raw.get("ntc_id"),
        "group_id": group_id,
        "assignment_sequence_number": sequence_number,
        "beam_name": raw.get("beam_name"),
        "emission_reception_code": raw.get("emi_rcp"),
        "frequency": {
            "center_mhz_source": raw.get("freq_mhz"), "minimum_mhz_source": raw.get("freq_min"),
            "maximum_mhz_source": raw.get("freq_max"), "bandwidth_khz_source": raw.get("bdwdth"),
        },
        "group": None if group is None else {
            "source_row": group["source_row"], "service_code": group_raw.get("srv_code"),
            "provision": group_raw.get("prov"), "frequency_min_mhz_source": group_raw.get("freq_min"),
            "frequency_max_mhz_source": group_raw.get("freq_max"), "bandwidth_khz_source": group_raw.get("bdwdth"),
        },
        # srv_cls.stn_cls codes of the group (ITU Preface Table 3); None when srv_cls was not extracted.
        "station_classes": None if station_classes is None else sorted(set(station_classes.get(group_id, []))),
        "emission_linkage": emission_linkage,
        "emissions": [{
            "source_row": row["source_row"], "emission_sequence_number": row["raw"].get("seq_no"),
            "emission_designator": row["raw"].get("design_emi"),
            "peak_envelope_power_dbw": row["raw"].get("pep_max"),
            "maximum_power_density_dbw_per_hz": row["raw"].get("pwr_ds_max"),
        } for row in selected],
        "satellite_beams": [{
            "source_row": row["source_row"], "maximum_isotropic_gain_db": row["raw"].get("gain"),
            "frequency_min_mhz_source": row["raw"].get("freq_min"),
            "frequency_max_mhz_source": row["raw"].get("freq_max"),
            "pattern_id": row["raw"].get("pattern_id"), "steerable_flag": row["raw"].get("f_steer"),
        } for row in beam_rows],
        "assumptions": assumptions,
        "missing_inputs": missing,
        "profile_ready": not missing,
        "calculation_status": "not_started",
    }


def assess_case(case, station, notice_profile, frequency_profiles):
    classification = case["regulatory_classification"]
    missing = []
    if station.get("longitude") is None or station.get("latitude") is None:
        missing.append("finnish_station_coordinates")
    missing.extend(notice_profile["missing_inputs"])
    ready_profiles = sum(profile["profile_ready"] for profile in frequency_profiles)
    for profile in frequency_profiles:
        missing.extend(profile["missing_inputs"])
    missing = sorted(set(missing))
    if classification["disposition"] == "eligible_with_specialist_review":
        readiness = "specialist_review_required"
    elif ready_profiles == len(frequency_profiles) and not missing:
        readiness = "ready_with_worst_case_assumptions"
    elif ready_profiles and notice_profile["orbit_context_ready"] and station.get("longitude") is not None and station.get("latitude") is not None:
        readiness = "partially_ready_with_worst_case_assumptions"
    else:
        readiness = "missing_required_input"
    assumptions = {"worst_case_satellite_beam_pointing"}
    for profile in frequency_profiles:
        assumptions.update(profile["assumptions"])
    return {
        "schema_version": 1,
        "case_id": case["case_id"],
        "readiness": readiness,
        "calculation_status": "not_started",
        "notice_profile_id": notice_profile["notice_profile_id"],
        "frequency_profile_ids": [profile["frequency_profile_id"] for profile in frequency_profiles],
        "frequency_profiles_total": len(frequency_profiles),
        "frequency_profiles_ready": ready_profiles,
        "missing_inputs": missing,
        "assumptions": sorted(assumptions),
        "frequency_relation": case.get("frequency_relation"),
        "matched_frequency_segments_hz": case.get("matched_frequency_segments_hz", []),
        "finnish_station": {
            "dataset_id": station["dataset_id"], "source_row": station["source_row"],
            "station_number": station["station_number"], "longitude": station.get("longitude"),
            "latitude": station.get("latitude"), "antenna_gain_db": station.get("antenna_gain_db"),
            "antenna_height_agl_m": station.get("antenna_height_agl_m"),
            "antenna_height_asl_m": station.get("antenna_height_asl_m"),
            "radiation_direction_deg": station.get("radiation_direction_deg"),
            "directivity": station.get("raw", {}).get("directivity"),
            "quality_flags": station.get("quality_flags", []),
        },
        "regulatory_classification": classification,
        "technical_calculations_performed": False,
    }


def run(prepared, queue_path, output):
    prepared, queue_path, output = prepared.resolve(), queue_path.resolve(), output.resolve()
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete") or manifest.get("errors"):
        raise ValueError("Preparation is incomplete")
    cases = list(_read_jsonl(queue_path))
    if not cases:
        raise ValueError("Calculation queue is empty")
    dataset_id = cases[0]["space"]["dataset_id"]
    if any(case["space"]["dataset_id"] != dataset_id for case in cases):
        raise ValueError("Readiness currently requires one space dataset per run")
    dataset = next((item for item in manifest["datasets"] if item["dataset_id"] == dataset_id), None)
    if dataset is None:
        raise ValueError("Queue space dataset is absent from preparation manifest")
    workbook_id = cases[0]["finnish_usage"]["dataset_id"]
    workbook = next((item for item in manifest["datasets"] if item["dataset_id"] == workbook_id), None)
    if workbook is None:
        raise ValueError("Queue Finnish dataset is absent from preparation manifest")
    required_tables = {"freq", "grp", "emiss", "s_beam", "geo", "non_geo", "orbit", "carrier_fr"}
    if missing_tables := required_tables - set(dataset["extraction"]["tables"]):
        raise ValueError(f"Prepared space dataset lacks tables: {sorted(missing_tables)}")

    wanted_frequency_rows = {row for case in cases for row in case["evidence"]["frequency_source_rows"]}
    frequency_rows = {row["source_row"]: row for row in _load_table(prepared, dataset, "freq") if row["source_row"] in wanted_frequency_rows}
    if missing_rows := wanted_frequency_rows - set(frequency_rows):
        raise ValueError(f"Frequency evidence rows absent from preparation: {len(missing_rows)}")
    groups = {row["raw"].get("grp_id"): row for row in _load_table(prepared, dataset, "grp")}
    emissions_by_group = {}
    for row in _load_table(prepared, dataset, "emiss"):
        emissions_by_group.setdefault(row["raw"].get("grp_id"), []).append(row)
    carrier_links = {}
    for row in _load_table(prepared, dataset, "carrier_fr"):
        raw = row["raw"]
        carrier_links.setdefault((raw.get("grp_id"), raw.get("seq_no")), []).append(raw.get("seq_emiss"))
    beams = {}
    for row in _load_table(prepared, dataset, "s_beam"):
        raw = row["raw"]
        beams.setdefault((raw.get("ntc_id"), raw.get("emi_rcp"), raw.get("beam_name")), []).append(row)
    geo_rows = _load_table(prepared, dataset, "geo")
    non_geo_rows = _load_table(prepared, dataset, "non_geo")
    orbit_rows = _load_table(prepared, dataset, "orbit")
    station_classes = None
    if "srv_cls" in dataset["extraction"]["tables"]:
        station_classes = {}
        for row in _load_table(prepared, dataset, "srv_cls"):
            if row["raw"].get("stn_cls"):
                station_classes.setdefault(row["raw"].get("grp_id"), []).append(row["raw"]["stn_cls"])
    received = {row["raw"].get("ntc_id"): row["raw"].get("d_rcv") for row in _load_table(prepared, dataset, "notice")}

    workbook_folder = _safe_path(prepared, workbook["output_directory"])
    station_path = _safe_path(workbook_folder, workbook["extraction"]["output"])
    stations = {row["source_row"]: row for row in _read_jsonl(station_path)}
    notice_objects = {case["space"]["notice_id"]: case["regulatory_classification"]["notice_object"] for case in cases}
    notice_profiles = {
        notice_id: build_notice_profile(dataset_id, notice_id, notice_object, geo_rows, non_geo_rows, orbit_rows)
        for notice_id, notice_object in notice_objects.items()
    }
    for notice_id, profile in notice_profiles.items():
        profile["notice_received_date"] = received.get(notice_id)
    profiles = {
        source_row: build_frequency_profile(dataset_id, row, groups, emissions_by_group, carrier_links, beams,
                                            station_classes)
        for source_row, row in frequency_rows.items()
    }

    output.mkdir(parents=True, exist_ok=True)
    notice_path = output / "notice_technical_profiles.jsonl"
    frequency_path = output / "frequency_technical_profiles.jsonl"
    readiness_path = output / "case_calculation_readiness.jsonl"
    csv_path = output / "case_calculation_readiness.csv"
    summary_path = output / "readiness_summary.json"
    with notice_path.open("w", encoding="utf-8") as stream:
        for profile in sorted(notice_profiles.values(), key=lambda item: item["notice_id"]):
            stream.write(json.dumps(profile, ensure_ascii=False, separators=(",", ":")) + "\n")
    with frequency_path.open("w", encoding="utf-8") as stream:
        for source_row in sorted(profiles):
            stream.write(json.dumps(profiles[source_row], ensure_ascii=False, separators=(",", ":")) + "\n")

    fields = (
        "case_id", "station_number", "station_source_row", "notice_id", "notice_object", "readiness",
        "frequency_profiles_total", "frequency_profiles_ready", "missing_inputs", "assumptions",
        "technical_calculations_performed",
    )
    counts, missing_counts, assumption_counts = {}, {}, {}
    case_results = []
    with readiness_path.open("w", encoding="utf-8") as json_stream, csv_path.open("w", encoding="utf-8", newline="") as csv_stream:
        writer = csv.DictWriter(csv_stream, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            source_rows = case["evidence"]["frequency_source_rows"]
            case_profiles = [profiles[row] for row in source_rows]
            station = stations.get(case["finnish_usage"]["source_row"])
            if station is None:
                raise ValueError("Finnish station evidence row is absent from preparation")
            notice_profile = notice_profiles[case["space"]["notice_id"]]
            result = assess_case(case, station, notice_profile, case_profiles)
            json_stream.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            case_results.append(result)
            counts[result["readiness"]] = counts.get(result["readiness"], 0) + 1
            for item in result["missing_inputs"]:
                missing_counts[item] = missing_counts.get(item, 0) + 1
            for item in result["assumptions"]:
                assumption_counts[item] = assumption_counts.get(item, 0) + 1
            writer.writerow({
                "case_id": result["case_id"], "station_number": station["station_number"],
                "station_source_row": station["source_row"], "notice_id": case["space"]["notice_id"],
                "notice_object": case["regulatory_classification"]["notice_object"],
                "readiness": result["readiness"], "frequency_profiles_total": result["frequency_profiles_total"],
                "frequency_profiles_ready": result["frequency_profiles_ready"],
                "missing_inputs": "|".join(result["missing_inputs"]), "assumptions": "|".join(result["assumptions"]),
                "technical_calculations_performed": result["technical_calculations_performed"],
            })
    summary = {
        "schema_version": 1, "method": METHOD, "method_version": METHOD_VERSION, "status": "completed",
        "scope": "input_assembly_and_readiness_only", "technical_calculations_performed": False,
        "input_cases": len(cases), "notice_profiles": len(notice_profiles), "frequency_profiles": len(profiles),
        "readiness_counts": dict(sorted(counts.items())), "missing_input_counts": dict(sorted(missing_counts.items())),
        "assumption_counts": dict(sorted(assumption_counts.items())),
        "source": {"title": "ITU BR IFIC (Space Services) Preface", "edition": "May 2026", "url": ITU_PREFACE_URL},
        "power_units": {"pep_max": "dBW", "pwr_ds_max": "dBW/Hz", "s_beam.gain": "dB"},
        "outputs": {
            "notice_profiles": notice_path.name, "frequency_profiles": frequency_path.name,
            "case_readiness_jsonl": readiness_path.name, "case_readiness_csv": csv_path.name,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
