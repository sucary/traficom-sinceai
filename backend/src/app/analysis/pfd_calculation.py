"""Worst-case pfd at Finnish stations and margins against RR Table 21-4.

Deterministic, free-space screening calculation. For each review case:

    pfd(δ) = P_ref + G_max - 10*log10(4*pi*d(δ)^2)        [dB(W/m2) in B_ref]

- P_ref: filed maximum power density (dBW/Hz) + 10*log10(B_ref), capped at the
  filed peak envelope power (the carrier cannot put more than its total power into
  the reference bandwidth). Worst emission of the case's frequency groups.
- G_max: maximum isotropic gain of the satellite beam; worst-case pointing at the
  station, as instructed by Traficom (beams can move; worst case always assumed).
- d(δ): slant range at angle of arrival δ. GSO: fixed geometry per station.
  Non-GSO: δ is swept from 0° to the highest elevation the orbit can reach over the
  station latitude, using the lowest filed altitude (perigee) for distance.

margin = limit(δ) - pfd(δ); the worst (smallest) margin over δ is reported.
A negative margin is a calculated exceedance of the Table 21-4 limit.
"""

import csv
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from ..reference.allocations import (
    APPLICABLE_RESULTS, article5_assessment, m4_assessment, sharing_basis,
)
from ..reference.services import criterion_tokens, load_station_classes, service_match
from ..reference.pfd_criteria import (
    CRITERIA_PATH, criteria_for, criterion_by_id, evaluate_formula, formula_variables, load_criteria, segment_at,
)


METHOD = "worst_case_pfd_free_space"
METHOD_VERSION = "1.3.1"
EARTH_RADIUS_KM = 6378.137
GSO_RADIUS_KM = 42164.0
ELEVATION_STEP_DEG = 0.1
DEFAULT_NEAR_MARGIN_DB = 3.0
REFERENCE_BANDWIDTHS_HZ = (4000, 1_000_000)
ASSUMPTIONS = [
    "Free-space spreading loss only (RR No. 21.16: limits relate to assumed free-space propagation).",
    "Spherical Earth, radius 6378.137 km; GSO orbit radius 42164 km; station height ignored.",
    "Satellite beam peak gain is assumed toward every Finnish station (Traficom: worst case always assumed).",
    "Power in the reference bandwidth = filed maximum power density (dBW/Hz) + 10*log10(B_ref), "
    "capped at the filed peak envelope power.",
    "The worst emission and the highest-gain beam among the case's frequency groups are combined.",
    "Non-GSO: angle of arrival swept 0°..max reachable elevation in 0.1° steps plus segment boundaries; "
    "distance uses the lowest filed altitude (perigee), visibility the highest (apogee).",
    "Non-GSO max elevation: sub-satellite latitude cannot exceed the inclination (or 180° - inclination).",
    "Adjacent (non-overlapping) cases use in-band pfd without out-of-band attenuation: an upper bound.",
    "A Table 21-4 row judges only emissions of groups whose ITU station class (srv_cls.stn_cls, IFIC Preface "
    "Table 3) matches one of the row's services; ambiguous or missing classes give candidate verdicts.",
    "RR No. 21.16 equal-rights sharing is checked per Region 1 sub-band of Article 5 (footnotes checked for "
    "Finland); spectrum where it fails is excluded. Finland's M4 table is reported as national context and does "
    "not change the legal result.",
]


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regulation_citation(criterion, document):
    """Portable, direct citation copied into every criterion evaluation."""
    source = document["sources"][criterion["source"]]
    return {
        "criterion_id": criterion["criterion_id"],
        "document": source["document"],
        "edition": source["edition"],
        "provision": criterion["provision"],
        "printed_page": criterion["location"]["printed_page"],
        "pdf_page": criterion["location"]["pdf_page"],
        "source_file": source["file"],
        "source_sha256": source["sha256"],
        "source_url": source["url"],
    }


def run_evidence(readiness_dir, cases_path, near_margin_db):
    """Deterministic run identity and hashes of every calculation input artifact."""
    paths = (
        ("review_cases", cases_path),
        ("case_readiness", readiness_dir / "case_calculation_readiness.jsonl"),
        ("notice_profiles", readiness_dir / "notice_technical_profiles.jsonl"),
        ("frequency_profiles", readiness_dir / "frequency_technical_profiles.jsonl"),
        ("pfd_criteria", CRITERIA_PATH),
    )
    artifacts = [
        {"role": role, "file": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size}
        for role, path in paths
    ]
    parameters = {
        "near_margin_db": near_margin_db,
        "earth_radius_km": EARTH_RADIUS_KM,
        "gso_orbit_radius_km": GSO_RADIUS_KM,
        "non_gso_elevation_step_deg": ELEVATION_STEP_DEG,
        "reference_bandwidths_hz": list(REFERENCE_BANDWIDTHS_HZ),
    }
    identity = json.dumps({
        "method": METHOD, "method_version": METHOD_VERSION,
        "parameters": parameters, "inputs": artifacts,
    }, sort_keys=True, separators=(",", ":"))
    return {
        "run_id": hashlib.sha256(identity.encode()).hexdigest(),
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "parameters": parameters,
        "input_artifacts": artifacts,
    }


def case_evidence(context, readiness_case, notice_profile, frequency_profiles, document):
    """Complete evidence chain needed to audit one record without upstream joins."""
    orbit_rows = []
    for table, key in (("geo", "geo_records"), ("non_geo", "non_geo_records"), ("orbit", "orbit_records")):
        orbit_rows.extend({"table": table, "source_row": row.get("source_row")}
                          for row in notice_profile.get(key, []))
    regulation_source = document["sources"]["RR2024-V1"]
    return {
        "source_datasets": {
            "space": {
                "dataset_id": context["space"]["dataset_id"],
                "sha256": context["space"]["dataset_id"],
                "file": context["space"]["file"],
                "issue": context["space"].get("issue"),
            },
            "finnish_workbook": {
                "dataset_id": context["finnish_usage"]["dataset_id"],
                "sha256": context["finnish_usage"]["dataset_id"],
                "file": context["finnish_usage"]["file"],
            },
        },
        "source_rows": {
            "notice": {"table": "notice", "source_row": context["space"].get("notice_source_row")},
            "orbit_context": orbit_rows,
            "frequency": [{"table": "freq", "source_row": profile.get("frequency_source_row")}
                          for profile in frequency_profiles],
            "group": [{"table": "grp", "source_row": profile["group"].get("source_row")}
                      for profile in frequency_profiles if profile.get("group")],
            "emission": sorted({row.get("source_row") for profile in frequency_profiles
                                for row in profile.get("emissions", []) if row.get("source_row") is not None}),
            "beam": sorted({row.get("source_row") for profile in frequency_profiles
                            for row in profile.get("satellite_beams", []) if row.get("source_row") is not None}),
            "finnish_station": {
                "table": context["finnish_usage"]["source_table"],
                "source_row": readiness_case["finnish_station"]["source_row"],
            },
        },
        "regulation_catalog": {
            "document": regulation_source["document"],
            "edition": regulation_source["edition"],
            "provision": "RR Article 21, No. 21.16, Table 21-4",
            "pdf_pages": [297, 298, 299, 300, 301],
            "source_file": regulation_source["file"],
            "source_sha256": regulation_source["sha256"],
            "source_url": regulation_source["url"],
            "transcription_status": document["transcription"]["status"],
        },
    }


# ----------------------------------------------------------------------------- geometry

def gso_geometry(station_lat_deg, station_lon_deg, satellite_lon_deg):
    """Elevation (deg) and slant range (km) from a station to a GSO satellite."""
    lat = math.radians(station_lat_deg)
    dlon = math.radians(((satellite_lon_deg - station_lon_deg + 180) % 360) - 180)
    cos_psi = math.cos(lat) * math.cos(dlon)
    psi = math.acos(max(-1.0, min(1.0, cos_psi)))
    distance = math.sqrt(EARTH_RADIUS_KM ** 2 + GSO_RADIUS_KM ** 2 - 2 * EARTH_RADIUS_KM * GSO_RADIUS_KM * cos_psi)
    if psi == 0:
        return 90.0, distance
    elevation = math.degrees(math.atan2(cos_psi - EARTH_RADIUS_KM / GSO_RADIUS_KM, math.sin(psi)))
    return elevation, distance


def slant_range_km(elevation_deg, altitude_km):
    """Distance from a ground point to a satellite at the given altitude seen at elevation."""
    e = math.radians(elevation_deg)
    r = EARTH_RADIUS_KM + altitude_km
    return math.sqrt(r ** 2 - (EARTH_RADIUS_KM * math.cos(e)) ** 2) - EARTH_RADIUS_KM * math.sin(e)


def elevation_at_central_angle(psi_deg, altitude_km):
    psi = math.radians(psi_deg)
    if psi == 0:
        return 90.0
    ratio = EARTH_RADIUS_KM / (EARTH_RADIUS_KM + altitude_km)
    return math.degrees(math.atan2(math.cos(psi) - ratio, math.sin(psi)))


def max_elevation_deg(station_lat_deg, inclination_deg, altitude_km):
    """Highest elevation at which a satellite in this orbit can be seen from the latitude."""
    reach = inclination_deg if inclination_deg <= 90 else 180 - inclination_deg
    gap = abs(station_lat_deg) - reach
    if gap <= 0:
        return 90.0
    return elevation_at_central_angle(gap, altitude_km)


def spreading_db(distance_km):
    return 10 * math.log10(4 * math.pi * (distance_km * 1000) ** 2)


# ----------------------------------------------------------------------------- emission

def power_in_reference_bandwidth(emission, reference_bandwidth_hz):
    """Return (dBW in B_ref, capped_by_peak_power) or None when no usable power is filed."""
    density = emission.get("maximum_power_density_dbw_per_hz")
    peak = emission.get("peak_envelope_power_dbw")
    if density is None:
        return None if peak is None else (peak, True)
    value = density + 10 * math.log10(reference_bandwidth_hz)
    if peak is not None and peak < value:
        return peak, True
    return value, False


def worst_emission(frequency_profiles, reference_bandwidth_hz, frequency_min_hz, frequency_max_hz):
    """Highest P_ref + G over profiles whose band touches [min, max]."""
    best = None
    for profile in frequency_profiles:
        lower, upper = profile_band_hz(profile)
        if lower is None or upper < frequency_min_hz or lower > frequency_max_hz:
            continue
        if frequency_min_hz < frequency_max_hz and not max(lower, frequency_min_hz) < min(upper, frequency_max_hz):
            continue  # only touches the edge: no shared spectrum
        gains =[beam["maximum_isotropic_gain_db"] for beam in profile.get("satellite_beams", [])
                 if beam.get("maximum_isotropic_gain_db") is not None]
        if not gains:
            continue
        gain = max(gains)
        beam = next(b for b in profile["satellite_beams"] if b.get("maximum_isotropic_gain_db") == gain)
        for emission in profile.get("emissions", []):
            power = power_in_reference_bandwidth(emission, reference_bandwidth_hz)
            if power is None:
                continue
            eirp = power[0] + gain
            if best is None or eirp > best["eirp_in_reference_bandwidth_dbw"]:
                best = {
                    "eirp_in_reference_bandwidth_dbw": eirp, "power_in_reference_bandwidth_dbw": power[0],
                    "capped_by_peak_envelope_power": power[1], "beam_gain_db": gain,
                    "frequency_profile_id": profile["frequency_profile_id"],
                    "frequency_source_row": profile.get("frequency_source_row"),
                    "group_id": profile.get("group_id"), "beam_name": profile.get("beam_name"),
                    "beam_source_row": beam.get("source_row"),
                    "emission_source_row": emission.get("source_row"),
                    "emission_designator": emission.get("emission_designator"),
                    "maximum_power_density_dbw_per_hz": emission.get("maximum_power_density_dbw_per_hz"),
                    "peak_envelope_power_dbw": emission.get("peak_envelope_power_dbw"),
                }
    return best


def profile_band_hz(profile):
    frequency = profile.get("frequency", {})
    lower, upper = frequency.get("minimum_mhz_source"), frequency.get("maximum_mhz_source")
    if lower is None or upper is None:
        center, width = frequency.get("center_mhz_source"), frequency.get("bandwidth_khz_source") or 0
        if center is None:
            return None, None
        lower, upper = center - width / 2000, center + width / 2000
    return math.floor(lower * 1e6), math.ceil(upper * 1e6)


# ----------------------------------------------------------------------------- constellation

def constellation_parameters(notice_profile):
    """X (No. 21.16.6) and Y (No. 21.16.15) where the filed data defines them."""
    orbits = notice_profile.get("orbit_records", [])
    non_geo = notice_profile.get("non_geo_records", [])
    satellites = sum(int(o.get("nbr_sat_pl") or 0) for o in orbits) or None
    parameters, notes, lower_bounds = {}, [], {}
    if satellites is not None:
        if satellites <= 50:
            parameters["X"] = 0.0
        elif satellites <= 288:
            parameters["X"] = 5 / 119 * (satellites - 50)
        elif satellites <= 999:
            parameters["X"] = (satellites + 402) / 69
        else:
            notes.append("X needs Nv (max visible satellites), not in the IFIC database, for N >= 1000.")
            # No. 21.16.6: X = max{20.3; 10 log Nv} for 1 000 <= N <= 6 000, X = 10 log Nv + 1 above (Nv >= 1).
            lower_bounds["X"] = 20.3 if satellites <= 6000 else 1.0
    north = max((int(r.get("nbr_sat_nh") or 0) for r in non_geo), default=0)
    south = max((int(r.get("nbr_sat_sh") or 0) for r in non_geo), default=0)
    if non_geo and (north or south):
        peak = max(north, south)
        parameters["Y"] = 0.0 if peak <= 2 else 5 * math.log10(peak)
    return {"satellites_in_constellation": satellites, "nn": north or None, "ns": south or None,
            "values": parameters, "lower_bounds": lower_bounds, "notes": notes}


def orbit_configurations(notice_profile, station_lat_deg):
    """Distinct (perigee, apogee, inclination) sets with their visibility from the station."""
    configs = {}
    for orbit in notice_profile.get("orbit_records", []):
        heights = [orbit.get(k) for k in ("perig_km", "apog_km", "op_ht_km") if orbit.get(k) is not None]
        inclination = orbit.get("inclin_ang")
        if not heights or inclination is None:
            continue
        perigee, apogee = min(heights), max(heights)
        key = (round(perigee, 1), round(apogee, 1), round(float(inclination), 2))
        entry = configs.setdefault(key, {"orbit_source_rows": []})
        entry["orbit_source_rows"].append(orbit.get("source_row"))
    result = []
    for (perigee, apogee, inclination), entry in sorted(configs.items()):
        top = max_elevation_deg(station_lat_deg, inclination, apogee)
        result.append({
            "perigee_km": perigee, "apogee_km": apogee, "inclination_deg": inclination,
            "max_elevation_deg": round(top, 3), "visible": top >= 0,
            "heo": apogee > 18000 and 35 <= inclination <= 145,
            "orbit_source_rows": entry["orbit_source_rows"],
        })
    return result


# ----------------------------------------------------------------------------- conditions

NGSO_FSS_CUTOFF_DATE = "1995-11-17"  # Nos. 21.16.6 / 21.16.6A


def condition_status(name, context):
    """Resolve a criterion condition from orbit, constellation, service and receipt date."""
    orbit, configs, constellation = context["orbit"], context["configs"], context["constellation"]
    if name == "heo":
        return "satisfied" if any(c["heo"] for c in configs) else "failed" if configs else "unresolved"
    if name == "non_heo":
        return "satisfied" if any(not c["heo"] for c in configs) else "failed" if configs else "unresolved"
    if name == "ngso_99_or_fewer_satellites":
        n = constellation["satellites_in_constellation"]
        return "unresolved" if n is None else "satisfied" if n <= 99 else "failed"
    if name == "gso_or_metsat_or_iss_or_pre1995_ngso_18.8_19.3":
        # No. 21.16.6A: MetSat space stations and GSO FSS/ISS; pre-17 Nov 1995 non-GSO FSS in
        # 18.8-19.3 GHz; No. 21.16.6B: HEO FSS under Resolution 147.
        classes = set(context["service_classes"])
        if orbit == "gso" or "EM" in classes:
            return "satisfied"
        if not classes or "ES" in classes or any(c["heo"] for c in configs):
            return "unresolved"
        received = (context.get("received_date") or "")[:10]
        if not received:
            return "unresolved"
        return "unresolved" if received <= NGSO_FSS_CUTOFF_DATE else "failed"
    return "unresolved"


def sharing_check(criterion, service, pieces):
    """Apply RR No. 21.16 equal-rights sharing per Region 1 sub-band, with M4 national context.

    Only spectrum where the satellite's service and the partner (fixed/mobile unless the row
    states otherwise) share with equal rights is kept for the calculation. The satellite
    services checked are the matched groups' services, or the row's services when the
    group service is unresolved.
    """
    row_tokens = set(criterion_tokens(criterion))
    if service["status"] == "matched":
        classes = load_station_classes()["classes"]
        tokens = row_tokens & {t for c in service["matched_classes"] for t in classes.get(c, {}).get("tokens", [])}
    else:
        tokens = row_tokens
    tokens = tokens or row_tokens
    article5, applicable = [], []
    for lower, upper in pieces:
        for result in article5_assessment(criterion, tokens, lower, upper):
            article5.append(result)
            if result["result"] in APPLICABLE_RESULTS:
                applicable.append((result["frequency_min_hz"], result["frequency_max_hz"]))
    check_segments = applicable or list(pieces)
    partners = sorted({p for lower, upper in check_segments for p in sharing_basis(criterion, lower, upper)["partners"]})
    m4 = [m4_assessment(partners, tokens, lower, upper) for lower, upper in check_segments]
    categories = [m["partner_in_finland"] for m in m4]
    national = ("primary" if "primary" in categories else "secondary" if "secondary" in categories else "not_listed")
    return {
        "satellite_services_checked": sorted(tokens),
        "article5_region1": article5,
        "applicable_segments_hz": sorted(set(applicable)),
        "rr_4_4_unallocated": any(r["result"] == "service_not_allocated" for r in article5),
        "m4_finland": {"partner_services": partners, "partner_in_finland": national,
                       "satellite_service_in_finland": next((m["satellite_service_in_finland"] for m in m4
                                                             if m["satellite_service_in_finland"] != "not_listed"),
                                                            "not_listed"),
                       "bands": [b for m in m4 for b in m["m4_bands"]]},
    }


def service_assessment(criterion, frequency_profiles):
    """Split a case's frequency groups by whether their service matches the criterion.

    Matching groups decide the verdict. Without any, ambiguous or unknown groups are used
    for a worst-case candidate value; if every group is a known mismatch, the row does
    not apply.
    """
    tokens = criterion_tokens(criterion)
    buckets = {"match": [], "ambiguous": [], "unknown": [], "no_match": []}
    for profile in frequency_profiles:
        buckets[service_match(profile.get("station_classes"), tokens)].append(profile)
    if buckets["match"]:
        status, profiles = "matched", buckets["match"]
    elif buckets["ambiguous"] or buckets["unknown"]:
        status, profiles = "unresolved", buckets["ambiguous"] + buckets["unknown"]
    else:
        status, profiles = "not_matched", []
    return {
        "status": status, "criterion_services": sorted(tokens), "profiles": profiles,
        "matched_classes": sorted({c for p in buckets["match"] for c in (p.get("station_classes") or [])}),
        "group_counts": {k: len(v) for k, v in buckets.items()},
        "station_classes_seen": sorted({c for p in frequency_profiles for c in (p.get("station_classes") or [])}),
    }


# ----------------------------------------------------------------------------- sweep

@lru_cache(maxsize=200_000)
def _sweep(criterion_id, parameter_items, altitude_km, max_elevation):
    """min over δ of limit(δ) + spreading(δ); independent of the emission level."""
    criterion = criterion_by_id(criterion_id)
    parameters = dict(parameter_items)
    angles = {round(i * ELEVATION_STEP_DEG, 6) for i in range(int(max_elevation / ELEVATION_STEP_DEG) + 1)}
    angles.add(max_elevation)
    for segment in criterion["segments"]:
        for edge in (segment["elev_min_deg"], segment["elev_max_deg"]):
            if edge <= max_elevation:
                angles.add(edge)
    best = None
    for angle in sorted(angles):
        formula = segment_at(criterion, angle)["formula"]
        try:
            limit = evaluate_formula(formula, angle, **parameters)
        except ValueError:
            continue  # e.g. log10 of a non-positive argument at an excluded endpoint
        spread = spreading_db(slant_range_km(angle, altitude_km))
        if best is None or limit + spread < best[0]:
            best = (limit + spread, angle, limit, spread)
    return best


def evaluate_criterion(criterion, eirp, orbit, geometry, parameters, lower_bounds=None):
    """Evaluate one criterion. Unknown X/Y with a known lower bound use the bound.

    Table 21-4 limits never increase with X or Y (checked in tests), so the lower bound
    gives the loosest possible limit: a negative margin then holds for every valid value,
    while a non-negative one cannot decide and is reported as parameter_missing.
    """
    needed = set().union(*(formula_variables(s["formula"]) for s in criterion["segments"])) - {"d"}
    missing = sorted(n for n in needed if n not in parameters)
    bounds = lower_bounds or {}
    if missing and any(n not in bounds for n in missing):
        return {"status": "parameter_missing", "missing_parameters": missing}
    if missing:
        result = evaluate_criterion(criterion, eirp, orbit, geometry, {**parameters, **{n: bounds[n] for n in missing}})
        if result.get("status") == "computed" and result["margin_db"] < 0:
            result["parameters_at_lower_bound"] = missing
            return result
        return {"status": "parameter_missing", "missing_parameters": missing,
                "bound_check": "not decisive: margin >= 0 at the loosest possible limit"}
    used = {n: parameters[n] for n in sorted(needed)}
    # Values stay at full precision; rounding happens only on export (see _rounded).
    if orbit == "gso":
        angle, distance = geometry["elevation_deg"], geometry["slant_range_km"]
        limit = evaluate_formula(segment_at(criterion, angle)["formula"], angle, **used)
        pfd = eirp - spreading_db(distance)
        return {"status": "computed", "parameters_used": used, "worst_elevation_deg": angle,
                "pfd_db": pfd, "limit_db": limit, "margin_db": limit - pfd,
                "max_pfd_db": pfd, "max_pfd_elevation_deg": angle}
    worst = None
    for config in geometry["configurations"]:
        if not config["visible"]:
            continue
        top = config["max_elevation_deg"]
        total, angle, limit, spread = _sweep(criterion["criterion_id"], tuple(sorted(used.items())),
                                             config["perigee_km"], top)
        candidate = {
            "status": "computed", "parameters_used": used, "worst_elevation_deg": angle,
            "pfd_db": eirp - spread, "limit_db": limit, "margin_db": total - eirp,
            "max_pfd_db": eirp - spreading_db(slant_range_km(top, config["perigee_km"])),
            "max_pfd_elevation_deg": top, "orbit_configuration": {
                k: config[k] for k in ("perigee_km", "apogee_km", "inclination_deg", "orbit_source_rows")},
        }
        if worst is None or candidate["margin_db"] < worst["margin_db"]:
            worst = candidate
    return worst or {"status": "not_visible"}


# ----------------------------------------------------------------------------- case

def relevant_intervals(readiness_case):
    segments = readiness_case.get("matched_frequency_segments_hz") or []
    if segments:
        return [(s["frequency_min_hz"], s["frequency_max_hz"]) for s in segments]
    return None  # adjacent: resolved from profiles and station band in calculate_case


def calculate_case(readiness_case, notice_profile, frequency_profiles, station_band, near_margin_db, document):
    station = readiness_case["finnish_station"]
    base = {
        "schema_version": 1, "method": METHOD, "method_version": METHOD_VERSION,
        "case_id": readiness_case["case_id"],
        "notice_id": notice_profile.get("notice_id") if notice_profile else None,
        "notice_object": notice_profile.get("notice_object") if notice_profile else None,
        "frequency_relation": (readiness_case.get("frequency_relation") or {}).get("relation"),
        "finnish_station": {k: station.get(k) for k in ("station_number", "source_row", "latitude", "longitude")},
        "readiness": readiness_case["readiness"],
    }
    if readiness_case["readiness"] not in ("ready_with_worst_case_assumptions", "partially_ready_with_worst_case_assumptions"):
        return {**base, "result": {"status": "missing_input", "missing_inputs": readiness_case.get("missing_inputs", [])}}
    object_kind = notice_profile["notice_object"]
    lat, lon = station["latitude"], station["longitude"]
    if object_kind == "geostationary_satellite_network":
        orbit = "gso"
        satellite_lon = next((g["long_nom"] for g in notice_profile["geo_records"] if g.get("long_nom") is not None), None)
        if satellite_lon is None:
            return {**base, "result": {"status": "missing_input", "missing_inputs": ["gso_longitude"]}}
        elevation, distance = gso_geometry(lat, lon, satellite_lon)
        geometry = {"orbit": "gso", "satellite_longitude_deg": satellite_lon,
                    "elevation_deg": elevation, "slant_range_km": distance, "visible": elevation >= 0}
        constellation = {"values": {}, "notes": [], "satellites_in_constellation": 1}
        configs = []
    elif object_kind == "non_geostationary_satellite_network":
        orbit = "non_gso"
        configs = orbit_configurations(notice_profile, lat)
        if not configs:
            return {**base, "result": {"status": "missing_input", "missing_inputs": ["non_gso_orbit_altitude"]}}
        constellation = constellation_parameters(notice_profile)
        geometry = {"orbit": "non_gso", "configurations": configs, "visible": any(c["visible"] for c in configs)}
    else:
        return {**base, "result": {"status": "not_space_station", "reason": f"notice object {object_kind}"}}
    base["geometry"] = geometry
    base["constellation"] = constellation
    if not geometry["visible"]:
        return {**base, "result": {"status": "not_visible",
                                   "reason": "Satellite is below the horizon from this station for every filed orbit."}}

    intervals = relevant_intervals(readiness_case)
    if intervals is None:
        guard = station_band["bandwidth_hz"] or 0
        window = (station_band["frequency_min_hz"] - guard, station_band["frequency_max_hz"] + guard)
        intervals = []
        for profile in frequency_profiles:
            lower, upper = profile_band_hz(profile)
            if lower is not None and lower <= window[1] and window[0] <= upper:
                intervals.append((max(lower, window[0]), min(upper, window[1])))
    # Group every frequency segment by criterion first, so a criterion is judged against
    # the worst emission over all of its segments, independent of segment order.
    grouped = {}
    for lower, upper in intervals:
        for match in criteria_for(lower, upper, orbit, document=document):
            if match["status"] != "criterion":
                continue
            entry = grouped.setdefault(match["criterion_id"], {"overlap": "inside", "pieces": []})
            if match["overlap"] == "partial":
                entry["overlap"] = "partial"
            for band in match["matched_bands"]:
                piece = (max(lower, band["frequency_min_hz"]), min(upper, band["frequency_max_hz"]))
                if piece[0] <= piece[1] and piece not in entry["pieces"]:
                    entry["pieces"].append(piece)
    evaluations = []
    for criterion_id in sorted(grouped):
        group = grouped[criterion_id]
        criterion = criterion_by_id(criterion_id, document)
        service = service_assessment(criterion, frequency_profiles)
        context = {"orbit": orbit, "configs": configs, "constellation": constellation,
                   "service_classes": service["matched_classes"],
                   "received_date": notice_profile.get("notice_received_date")}
        conditions = {name: condition_status(name, context) for name in criterion["conditions"]}
        sharing = sharing_check(criterion, service, sorted(group["pieces"]))
        if service["status"] == "not_matched" or "failed" in conditions.values():
            applicability = "not_applicable"
        elif not sharing["applicable_segments_hz"]:
            applicability = "not_applicable"
        elif service["status"] == "unresolved":
            applicability = "service_unresolved"
        elif "unresolved" in conditions.values():
            applicability = "conditions_unresolved"
        else:
            applicability = "applicable"
        usable_profiles = service["profiles"]
        emission = None
        for piece in sharing["applicable_segments_hz"]:
            candidate = worst_emission(usable_profiles, criterion["reference_bandwidth_hz"], *piece)
            if candidate and (emission is None or candidate["eirp_in_reference_bandwidth_dbw"]
                              > emission["eirp_in_reference_bandwidth_dbw"]):
                emission = candidate
        entry = {"criterion_id": criterion_id, "reference_bandwidth_hz": criterion["reference_bandwidth_hz"],
                 "band_overlap": group["overlap"], "evaluated_segments_hz": sharing["applicable_segments_hz"],
                 "service": {k: v for k, v in service.items() if k != "profiles"},
                 "conditions": conditions, "sharing": sharing, "applicability": applicability,
                 "regulation_citation": regulation_citation(criterion, document),
                 "caveats": evaluation_caveats(criterion, max(p[1] for p in group["pieces"]))}
        if not sharing["applicable_segments_hz"]:
            entry["not_applicable_reason"] = "rr_21_16_equal_rights_sharing_not_met"
        if applicability == "not_applicable":
            entry["status"] = "not_applicable"
        elif emission is None:
            entry.update({"status": "missing_input", "missing_inputs": ["usable_power_or_gain"]})
        else:
            entry["emission"] = emission
            entry.update(evaluate_criterion(criterion, emission["eirp_in_reference_bandwidth_dbw"], orbit,
                                            geometry, constellation["values"], constellation.get("lower_bounds")))
            apply_special_method(entry, criterion)
        evaluations.append(entry)
    base["evaluations"] = evaluations
    base["result"] = case_result(evaluations, near_margin_db, constellation)
    governing_id = base["result"].get("governing_criterion_id")
    if governing_id:
        base["result"]["regulation_citation"] = next(
            entry["regulation_citation"] for entry in evaluations if entry["criterion_id"] == governing_id
        )
    if base["result"]["status"] in ("no_criterion", "parameter_missing", "special_method_required",
                                    "unallocated_service_rr_4_4"):
        base["result"]["reference_pfd"] = reference_pfd(frequency_profiles, intervals, orbit, geometry)
    return _rounded(base)


CONFIRMED_APPLICABILITY = {"applicable"}


def margin_class(margin_db, near_margin_db):
    """Classify at full precision; -0.004 dB is an exceedance, 2.996 dB is near the limit."""
    return "exceeds_limit" if margin_db < 0 else "near_limit" if margin_db < near_margin_db else "below_limit"


def apply_special_method(entry, criterion):
    """Withhold verdicts where the regulation prescribes a different calculation method.

    The generic value is kept as ``screening_estimate``. It still supports a verdict only
    when the criterion states that the generic value is a proven upper bound of the
    official quantity and the margin is non-negative.
    """
    special = criterion.get("special_method")
    if not special or entry.get("status") != "computed":
        return
    if special["generic_is_upper_bound"] and entry["margin_db"] >= 0:
        entry["special_method_note"] = (
            f"{special['provision']} prescribes {special['method']}; the generic value is an upper bound of it, "
            "so this non-negative margin holds."
        )
        return
    entry["screening_estimate"] = {k: entry.pop(k) for k in (
        "worst_elevation_deg", "pfd_db", "limit_db", "margin_db", "max_pfd_db", "max_pfd_elevation_deg")}
    entry["status"] = "special_method_required"
    entry["special_method"] = {k: special[k] for k in ("provision", "method", "required_inputs", "upper_bound_reason")}


def unallocated_rows(evaluations):
    """Rows where a group of the row's service has no Region 1 allocation in the band (RR No. 4.4)."""
    return [
        {"criterion_id": e["criterion_id"], "satellite_services": e["sharing"]["satellite_services_checked"],
         "segments_hz": [(r["frequency_min_hz"], r["frequency_max_hz"]) for r in e["sharing"]["article5_region1"]
                         if r["result"] == "service_not_allocated"]}
        for e in evaluations
        if e.get("sharing", {}).get("rr_4_4_unallocated") and e["service"]["status"] == "matched"
    ]


def case_result(evaluations, near_margin_db, constellation):
    result = _case_result(evaluations, near_margin_db, constellation)
    unallocated = unallocated_rows(evaluations)
    if unallocated:
        result["rr_4_4_unallocated_rows"] = unallocated
        if result["status"] == "no_criterion":
            result["status"] = "unallocated_service_rr_4_4"
            result["reason"] = ("The satellite's service has no Region 1 allocation in this band, so no Table 21-4 "
                                "limit applies; under RR No. 4.4 it must not cause harmful interference and cannot "
                                "claim protection.")
    return result


def _case_result(evaluations, near_margin_db, constellation):
    live = [e for e in evaluations if e["applicability"] != "not_applicable"]
    computed = [e for e in live if e.get("status") == "computed"]
    confirmed_rows = [e for e in computed if e["applicability"] in CONFIRMED_APPLICABILITY]
    if computed:
        # A confirmed row decides the verdict; unconfirmed rows only decide when none is confirmed.
        governing = min(confirmed_rows or computed, key=lambda e: e["margin_db"])
        margin_kind = margin_class(governing["margin_db"], near_margin_db)
        confirmed = governing["applicability"] in CONFIRMED_APPLICABILITY
        stricter_unconfirmed = [
            {"criterion_id": e["criterion_id"], "applicability": e["applicability"], "margin_db": e["margin_db"]}
            for e in computed if confirmed and e not in confirmed_rows and e["margin_db"] < governing["margin_db"]
        ]
        return {
            "national_context_m4": governing["sharing"]["m4_finland"]["partner_in_finland"],
            "stricter_unconfirmed_rows": stricter_unconfirmed,
            "status": margin_kind if confirmed else f"candidate_{margin_kind}",
            "margin_class": margin_kind, "applicability_confirmed": confirmed,
            "worst_margin_db": governing["margin_db"], "governing_criterion_id": governing["criterion_id"],
            "governing_applicability": governing["applicability"],
            "pfd_db": governing["pfd_db"], "limit_db": governing["limit_db"],
            "reference_bandwidth_hz": governing["reference_bandwidth_hz"],
            "worst_elevation_deg": governing["worst_elevation_deg"],
            "withheld_criteria": [
                {"criterion_id": e["criterion_id"], "status": e["status"]}
                for e in live if e.get("status") in ("special_method_required", "parameter_missing")
            ],
        }
    statuses = {e.get("status") for e in live}
    if "special_method_required" in statuses:
        return {"status": "special_method_required",
                "criteria": [e["criterion_id"] for e in live if e.get("status") == "special_method_required"]}
    if "parameter_missing" in statuses:
        return {"status": "parameter_missing",
                "missing_parameters": sorted({p for e in live for p in e.get("missing_parameters", [])}),
                "notes": constellation.get("notes", [])}
    if live:
        return {"status": "missing_input"}
    return {"status": "no_criterion"}


_ROUNDING = {"pfd_db": 2, "limit_db": 2, "margin_db": 2, "max_pfd_db": 2, "worst_margin_db": 2,
             "worst_elevation_deg": 3, "max_pfd_elevation_deg": 3, "elevation_deg": 3, "slant_range_km": 1}


def _rounded(value):
    """Round exported numbers only after every classification has been made."""
    if isinstance(value, dict):
        return {k: (round(v, _ROUNDING[k]) if k in _ROUNDING and isinstance(v, float) else _rounded(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def evaluation_caveats(criterion, frequency_hz):
    """Known ways the screening value can differ from the regulatory quantity (all pessimistic)."""
    caveats = []
    if criterion["reference_bandwidth_hz"] > 4000 and frequency_hz < 15e9:
        caveats.append(
            "density_scaled_from_worst_4khz: below 15 GHz the filed maximum power density is averaged over "
            "the worst 4 kHz (RR Appendix 4, footnote 2 to Tables A-D); scaling it to the reference bandwidth "
            "assumes a flat spectrum and can overstate pfd"
        )
    if "21.16.8" in criterion["footnotes"]:
        caveats.append(
            "mean_pfd_limit: the limit is a mean pfd including SAR duty cycle (No. 21.16.8); filed peak values "
            "overstate it"
        )
    return caveats


def reference_pfd(frequency_profiles, intervals, orbit, geometry):
    """Maximum pfd in 4 kHz and 1 MHz for cases without an applicable limit (expert context)."""
    if orbit == "gso":
        distance = geometry["slant_range_km"]
    else:
        visible = [c for c in geometry["configurations"] if c["visible"]]
        distance = min(slant_range_km(c["max_elevation_deg"], c["perigee_km"]) for c in visible)
    result = {}
    for bandwidth in REFERENCE_BANDWIDTHS_HZ:
        best = None
        for lower, upper in intervals:
            emission = worst_emission(frequency_profiles, bandwidth, lower, upper)
            if emission and (best is None or emission["eirp_in_reference_bandwidth_dbw"] > best):
                best = emission["eirp_in_reference_bandwidth_dbw"]
        result[f"max_pfd_db_per_{bandwidth}_hz"] = None if best is None else round(best - spreading_db(distance), 2)
    return result


# ----------------------------------------------------------------------------- run

def _read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def run(readiness_dir, cases_path, output, near_margin_db=DEFAULT_NEAR_MARGIN_DB):
    readiness_dir, cases_path, output = readiness_dir.resolve(), cases_path.resolve(), output.resolve()
    document = load_criteria()
    run_context = run_evidence(readiness_dir, cases_path, near_margin_db)
    notices = {p["notice_profile_id"]: p for p in _read_jsonl(readiness_dir / "notice_technical_profiles.jsonl")}
    profiles = {p["frequency_profile_id"]: p for p in _read_jsonl(readiness_dir / "frequency_technical_profiles.jsonl")}
    review = {}
    for case in _read_jsonl(cases_path):
        finnish, space = case["finnish_usage"], case["space"]
        review[case["case_id"]] = {
            "band": {k: finnish[k] for k in ("frequency_min_hz", "frequency_max_hz", "bandwidth_hz", "center_hz")},
            "frequency_role": finnish["frequency_role"],
            "space": {k: space.get(k) for k in ("dataset_id", "file", "dataset_kind", "issue", "notice_source_row",
                                                 "notice_id", "administration", "notice_type", "provision", "action_code")},
            "finnish_usage": {k: finnish.get(k) for k in (
                "dataset_id", "file", "source_table", "source_row", "station_number"
            )},
            "satellite_names": sorted({s["satellite_name"] for s in space.get("satellites", []) if s.get("satellite_name")}),
        }
    output.mkdir(parents=True, exist_ok=True)
    jsonl_path = output / "case_pfd_results.jsonl"
    csv_path = output / "case_pfd_results.csv"
    summary_path = output / "pfd_summary.json"
    fields = ("run_id", "case_id", "space_file", "space_dataset_id", "space_sha256", "notice_source_row",
              "notice_id", "administration", "satellite_names", "provision", "action_code",
              "orbit", "station_number", "frequency_role", "protected_center_hz", "frequency_relation", "status", "margin_class",
              "applicability_confirmed",
              "worst_margin_db", "pfd_db", "limit_db", "reference_bandwidth_hz", "worst_elevation_deg",
              "governing_criterion_id", "governing_applicability", "orbit_source_rows",
              "finnish_dataset_id", "finnish_sha256", "finnish_source_row",
              "regulation_edition", "regulation_provision", "regulation_pdf_page", "regulation_source_sha256",
              "run_parameters", "run_input_hashes")
    counts, by_dataset = {}, {}
    with jsonl_path.open("w", encoding="utf-8") as json_stream, csv_path.open("w", encoding="utf-8", newline="") as csv_stream:
        writer = csv.DictWriter(csv_stream, fieldnames=fields)
        writer.writeheader()
        for readiness_case in _read_jsonl(readiness_dir / "case_calculation_readiness.jsonl"):
            context = review[readiness_case["case_id"]]
            notice_profile = notices.get(readiness_case["notice_profile_id"])
            frequency_profiles = [profiles[i] for i in readiness_case["frequency_profile_ids"] if i in profiles]
            result = calculate_case(
                readiness_case, notice_profile, frequency_profiles,
                context["band"], near_margin_db, document,
            )
            result["space"] = context["space"]
            result["satellite_names"] = context["satellite_names"]
            result["finnish_station"]["frequency_role"] = context["frequency_role"]
            result["finnish_station"]["protected_band"] = context["band"]
            result["assumptions"] = ASSUMPTIONS
            result["run"] = run_context
            result["evidence"] = case_evidence(context, readiness_case, notice_profile, frequency_profiles, document)
            json_stream.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            outcome = result["result"]
            citation = outcome.get("regulation_citation", {})
            orbit_source_rows = result["evidence"]["source_rows"]["orbit_context"]
            writer.writerow({
                "run_id": run_context["run_id"], "case_id": result["case_id"],
                "space_file": context["space"]["file"],
                "space_dataset_id": context["space"]["dataset_id"], "space_sha256": context["space"]["dataset_id"],
                "notice_source_row": context["space"]["notice_source_row"],
                "notice_id": context["space"]["notice_id"], "administration": context["space"]["administration"],
                "satellite_names": "|".join(context["satellite_names"]), "provision": context["space"]["provision"],
                "action_code": context["space"]["action_code"],
                "orbit": (result.get("geometry") or {}).get("orbit"),
                "station_number": result["finnish_station"]["station_number"],
                "frequency_role": context["frequency_role"], "protected_center_hz": context["band"]["center_hz"],
                "frequency_relation": result["frequency_relation"], "status": outcome["status"],
                "margin_class": outcome.get("margin_class"),
                "applicability_confirmed": outcome.get("applicability_confirmed"),
                "worst_margin_db": outcome.get("worst_margin_db"), "pfd_db": outcome.get("pfd_db"),
                "limit_db": outcome.get("limit_db"), "reference_bandwidth_hz": outcome.get("reference_bandwidth_hz"),
                "worst_elevation_deg": outcome.get("worst_elevation_deg"),
                "governing_criterion_id": outcome.get("governing_criterion_id"),
                "governing_applicability": outcome.get("governing_applicability"),
                "orbit_source_rows": "|".join(f"{row['table']}:{row['source_row']}" for row in orbit_source_rows),
                "finnish_dataset_id": context["finnish_usage"]["dataset_id"],
                "finnish_sha256": context["finnish_usage"]["dataset_id"],
                "finnish_source_row": context["finnish_usage"]["source_row"],
                "regulation_edition": citation.get("edition"), "regulation_provision": citation.get("provision"),
                "regulation_pdf_page": citation.get("pdf_page"),
                "regulation_source_sha256": citation.get("source_sha256"),
                "run_parameters": json.dumps(run_context["parameters"], sort_keys=True, separators=(",", ":")),
                "run_input_hashes": "|".join(f"{item['role']}:{item['sha256']}" for item in run_context["input_artifacts"]),
            })
            counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
            dataset = by_dataset.setdefault(context["space"]["file"], {"counts": {}, "notices_exceeding": set(),
                                                                      "notices_near": set()})
            dataset["counts"][outcome["status"]] = dataset["counts"].get(outcome["status"], 0) + 1
            if outcome.get("margin_class") == "exceeds_limit":
                dataset["notices_exceeding"].add(context["space"]["notice_id"])
            if outcome.get("margin_class") == "near_limit":
                dataset["notices_near"].add(context["space"]["notice_id"])
    summary = {
        "schema_version": 1, "method": METHOD, "method_version": METHOD_VERSION, "status": "completed",
        "run": run_context,
        "near_margin_db": near_margin_db, "criteria_transcription_status": document["transcription"]["status"],
        "status_definitions": {
            "exceeds_limit": "Worst-case pfd above an applicable Table 21-4 limit (margin < 0 dB).",
            "near_limit": f"Margin between 0 and {near_margin_db} dB against an applicable limit.",
            "below_limit": f"Margin of at least {near_margin_db} dB against an applicable limit.",
            "candidate_*": "Same margin classes, but no row is confirmed applicable: the group's station "
                           "class is ambiguous or missing, or a footnote condition is unresolved.",
            "special_method_required": "Only rows whose regulation prescribes a special method (No. 21.16.8 "
                                       "SAR mean pfd, No. 21.16.19 Resolution 679) apply, and the generic "
                                       "value cannot decide; generic estimate kept for context.",
            "no_criterion": "No applicable Table 21-4 row; reference pfd in 4 kHz and 1 MHz is reported.",
            "parameter_missing": "Applicable row needs a constellation parameter not in the database.",
            "not_visible": "Satellite cannot be above the horizon at this station.",
            "unallocated_service_rr_4_4": "The satellite's service has no Region 1 allocation in the band (RR "
                                          "No. 4.4): no Table 21-4 limit, no right to cause interference or "
                                          "claim protection; reference pfd reported.",
            "missing_input": "Required technical input missing.",
            "not_space_station": "Notice is not a space station (e.g. specific earth station).",
        },
        "assumptions": ASSUMPTIONS, "counts": dict(sorted(counts.items())),
        "datasets": {
            name: {"counts": dict(sorted(d["counts"].items())), "notices_with_candidate_or_confirmed_exceedance": len(d["notices_exceeding"]),
                   "notices_near_limit": len(d["notices_near"])}
            for name, d in sorted(by_dataset.items())
        },
        "outputs": {"jsonl": jsonl_path.name, "csv": csv_path.name},
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
