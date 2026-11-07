"""Check RR No. 21.16 "shared with equal rights" against Article 5 Region 1 and Finland's M4.

No. 21.16: Table 21-4 limits apply "to emissions by a space station of the service
indicated where the frequency bands are shared with equal rights with the fixed or
mobile service, unless otherwise stated".

- Legal test (Article 5, Region 1, footnotes checked for Finland): in each Region 1
  sub-band, the satellite's service must hold an allocation usable by a transmitting
  space station (space-to-Earth, space-to-space or no stated direction), and a partner
  service (fixed or mobile, unless the row states another basis) must hold an allocation
  of the same category. Primary/primary and secondary/secondary are equal rights.
- National context (M4): whether Finland's Frequency Allocation Table lists the partner
  service in the band, and with which category. M4 lists services "in use or intended to
  be used" in Finland, so it can be narrower than Region 1; it does not change the legal
  result, it tells the expert whether there is national fixed/mobile use to protect.
"""

from functools import lru_cache
import json
from pathlib import Path
import re


ARTICLE5_PATH = Path(__file__).with_name("article5_region1.json")
M4_FILE = "docs/reference/traficom-m4/Taajuusjakotaulukko_api_v13_2026-11-07.json"
DEFAULT_PARTNERS = ("FIXED", "MOBILE")
TRANSMITTING = {"space-to-Earth", "space-to-space"}
_UNIT = {"khz": 1e3, "mhz": 1e6, "ghz": 1e9}
_RANK = {"primary": 2, "secondary": 1}


@lru_cache(maxsize=1)
def load_article5(path=ARTICLE5_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _hz(text):
    match = re.fullmatch(r"\s*([0-9][0-9 ]*(?:\.[0-9]+)?)\s*(kHz|MHz|GHz)\s*", text or "", re.I)
    if not match:
        raise ValueError(f"Unparseable M4 frequency: {text!r}")
    return int(round(float(match[1].replace(" ", "")) * _UNIT[match[2].lower()]))


def m4_service_tokens(name):
    """Map an M4 'Services_in_Finland' string to (tokens, category, directions)."""
    raw = name.strip()
    letters = re.sub(r"[^A-Za-z]", "", raw.split("(")[0])
    category = "primary" if letters and letters == letters.upper() else "secondary"
    text = raw.upper()
    head = text.split("(")[0].strip()
    directions = sorted({d for d, key in (("space-to-Earth", "SPACE-TO-EARTH"), ("Earth-to-space", "EARTH-TO-SPACE"),
                                          ("space-to-space", "SPACE-TO-SPACE")) if key in text})
    if head in ("FIXED AND MOBILE", "MOBILE AND FIXED"):
        tokens = {"FIXED", "MOBILE"}
    elif head.startswith(("FIXED SATELLITE", "FIXED-SATELLITE")):
        tokens = {"FSS"}
    elif head == "FIXED":
        tokens = {"FIXED"}
    elif "MOBILE-SATELLITE" in head or "MOBILE SATELLITE" in head:
        tokens = {"MSS"}
    elif "MOBILE" in head:
        tokens = {"MOBILE"}
    elif head == "METEOROLOGICAL AIDS":
        tokens = {"METAIDS"}
    elif head.startswith("METEOROLOGICAL"):
        tokens = {"METSAT"}
    elif head.startswith("EARTH EXPLORATION"):
        tokens = {"EESS_PASSIVE"} if "PASSIVE" in text else {"EESS", "EESS_ACTIVE"} if "ACTIVE" in text else {"EESS"}
    elif head.startswith("SPACE RESEARCH"):
        tokens = {"SR_PASSIVE"} if "PASSIVE" in text else {"SR"}
    elif head.startswith("SPACE OPERATION"):
        tokens = {"SO"}
    elif head.startswith("INTER-SATELLITE"):
        tokens = {"ISS"}
    elif head.startswith("BROADCASTING-SATELLITE") or head.startswith("BROADCASTING SATELLITE"):
        tokens = {"BSS"}
    elif head == "BROADCASTING":
        tokens = {"BROADCASTING"}
    elif head.startswith("RADIODETERMINATION"):
        tokens = {"RDSS"}
    else:
        tokens = {"OTHER:" + head}
    return tokens, category, directions


@lru_cache(maxsize=1)
def load_m4(path=None):
    """M4 bands with their services, one entry per (band lower, band upper)."""
    if path is None:
        from ..config import PROJECT_ROOT
        path = PROJECT_ROOT / M4_FILE
    records = json.loads(Path(path).read_text(encoding="utf-8"))["value"]
    bands = {}
    for record in records:
        key = (_hz(record["Frequency_band_lower_limit"]), _hz(record["Frequency_band_upper_limit"]))
        band = bands.setdefault(key, {"frequency_min_hz": key[0], "frequency_max_hz": key[1],
                                      "label": f'{record["Frequency_band_lower_limit"]} - {record["Frequency_band_upper_limit"]}',
                                      "services": {}, "record_ids": []})
        band["record_ids"].append(record["ID"])
        name = record["Services_in_Finland"].strip()
        if name and name not in band["services"]:
            tokens, category, directions = m4_service_tokens(name)
            band["services"][name] = {"tokens": sorted(tokens), "category": category, "directions": directions}
    return sorted(bands.values(), key=lambda b: (b["frequency_min_hz"], b["frequency_max_hz"]))


def _overlaps(entry, lower, upper):
    if lower == upper:
        return entry["frequency_min_hz"] <= lower <= entry["frequency_max_hz"]
    return max(lower, entry["frequency_min_hz"]) < min(upper, entry["frequency_max_hz"])


def _best(categories):
    return max(categories, key=lambda c: _RANK[c], default=None)


def sharing_basis(criterion, lower, upper):
    """Partner services and basis for a criterion in [lower, upper]: default or row-specific."""
    for override in criterion.get("sharing_basis", []):
        if override["frequency_min_hz"] <= lower and upper <= override["frequency_max_hz"]:
            return override
    return {"partners": list(DEFAULT_PARTNERS), "basis": "No. 21.16 (fixed or mobile service)"}


def article5_assessment(criterion, service_tokens, lower, upper, document=None):
    """Per Region 1 sub-band verdict on equal-rights sharing for the given services.

    Returns a list of sub-band results; ``result`` is one of:
    equal_rights, explicitly_applicable, unequal_rights, partner_not_allocated,
    service_not_allocated (the space service has no transmitting allocation: RR No. 4.4),
    no_article5_entry.
    """
    document = document or load_article5()
    results = []
    covered = []
    for band in document["bands"]:
        if not _overlaps(band, lower, upper):
            continue
        piece = (max(lower, band["frequency_min_hz"]), min(upper, band["frequency_max_hz"]))
        covered.append(piece)
        basis = sharing_basis(criterion, *piece)
        allocations = band["allocations"]
        space = _best([a["category"] for a in allocations if a["service"] in service_tokens
                       and (not a.get("directions") or TRANSMITTING & set(a["directions"]))])
        partner = _best([a["category"] for a in allocations if a["service"] in basis["partners"]])
        if basis.get("explicit"):
            result = "explicitly_applicable"
        elif space is None:
            result = "service_not_allocated"
        elif partner is None:
            result = "partner_not_allocated"
        elif space == partner:
            result = "equal_rights"
        else:
            result = "unequal_rights"
        results.append({
            "frequency_min_hz": piece[0], "frequency_max_hz": piece[1], "article5_band": band["label"],
            "location": band["location"], "service_category": space, "partner_services": basis["partners"],
            "partner_category": partner, "basis": basis["basis"], "result": result,
        })
    # Report uncovered spectrum explicitly rather than silently passing it.
    cursor = lower
    for start, end in sorted(covered):
        if start > cursor:
            results.append({"frequency_min_hz": cursor, "frequency_max_hz": start, "result": "no_article5_entry"})
        cursor = max(cursor, end)
    if cursor < upper or not covered:
        results.append({"frequency_min_hz": cursor, "frequency_max_hz": upper, "result": "no_article5_entry"})
    return sorted(results, key=lambda r: r["frequency_min_hz"])


APPLICABLE_RESULTS = {"equal_rights", "explicitly_applicable"}


def m4_assessment(partners, service_tokens, lower, upper, bands=None):
    """Finland's M4 categories for the partner services and the satellite service."""
    bands = load_m4() if bands is None else bands
    found = []
    for band in bands:
        if not _overlaps(band, lower, upper):
            continue
        partner = _best([s["category"] for s in band["services"].values() if set(s["tokens"]) & set(partners)])
        space = _best([s["category"] for s in band["services"].values() if set(s["tokens"]) & set(service_tokens)])
        found.append({"m4_band": band["label"], "partner_category": partner, "service_category": space,
                      "services": sorted(band["services"]), "record_ids": band["record_ids"][:5]})
    partner = _best([f["partner_category"] for f in found if f["partner_category"]])
    return {
        "partner_in_finland": partner or "not_listed",
        "satellite_service_in_finland": _best([f["service_category"] for f in found if f["service_category"]]) or "not_listed",
        "m4_bands": found,
    }
