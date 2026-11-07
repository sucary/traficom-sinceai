"""Decide whether a satellite group's service matches the services of a Table 21-4 row.

Rows name services in prose ("Fixed-satellite (space-to-Earth)"); groups carry ITU
station-class codes (srv_cls.stn_cls, e.g. "EC"). Both are mapped to service tokens
from ``station_classes.json`` (ITU BR IFIC Preface, Section IV, Table 3).
"""

from functools import lru_cache
import json
from pathlib import Path


CLASSES_PATH = Path(__file__).with_name("station_classes.json")
# Most specific prefixes first.
_SERVICE_PREFIXES = (
    ("Mobile-satellite (except aeronautical", "MSS_EXCEPT_AERO"),
    ("Earth exploration-satellite (active)", "EESS_ACTIVE"),
    ("Fixed-satellite", "FSS"),
    ("Broadcasting-satellite", "BSS"),
    ("Mobile-satellite", "MSS"),
    ("Radiodetermination-satellite", "RDSS"),
    ("Meteorological-satellite", "METSAT"),
    ("Earth exploration-satellite", "EESS"),
    ("Space research", "SR"),
    ("Space operation", "SO"),
    ("Inter-satellite", "ISS"),
)


@lru_cache(maxsize=1)
def load_station_classes(path=CLASSES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def service_token(service_text):
    for prefix, token in _SERVICE_PREFIXES:
        if service_text.startswith(prefix):
            return token
    raise ValueError(f"Unmapped Table 21-4 service: {service_text!r}")


def criterion_tokens(criterion):
    return frozenset(service_token(text) for text in criterion["services"])


def service_match(station_classes, tokens, document=None):
    """Return "match", "ambiguous", "no_match" or "unknown" for one group.

    ``station_classes`` is the list of srv_cls codes of the group; None or empty means
    the service is not known.
    """
    if not station_classes:
        return "unknown"
    classes = (document or load_station_classes())["classes"]
    ambiguous = unknown = False
    for code in station_classes:
        entry = classes.get(code)
        if entry is None:
            unknown = True  # earth-station or unlisted code
            continue
        if tokens & set(entry["tokens"]):
            return "match"
        if entry.get("ambiguous_for_all_other_services") or tokens & set(entry.get("ambiguous_for", [])):
            ambiguous = True
    if ambiguous:
        return "ambiguous"
    return "unknown" if unknown else "no_match"
