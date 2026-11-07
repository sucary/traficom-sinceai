"""Look up space-station pfd criteria (RR Article 21, Table 21-4) for a satellite band.

The criteria live in ``pfd_criteria.json`` next to this module. Each criterion holds
piecewise formulas of the angle of arrival ``d`` (degrees) and, for some rows, the
constellation parameters ``X`` (No. 21.16.6) or ``Y`` (No. 21.16.15). Formulas are
parsed with a whitelist evaluator; nothing is passed to ``eval``.

This module only selects and evaluates criteria. It does not compute pfd values.
"""

import ast
from functools import lru_cache
import json
import math
from pathlib import Path


CRITERIA_PATH = Path(__file__).with_name("pfd_criteria.json")
ORBITS = {"gso", "non_gso"}
_BINARY = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
           ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}
_UNARY = {ast.USub: lambda a: -a, ast.UAdd: lambda a: a}
_FUNCTIONS = {"log10": math.log10}
VARIABLES = frozenset({"d", "X", "Y"})


def _compile(formula):
    tree = ast.parse(formula, mode="eval")
    for node in ast.walk(tree):
        allowed = (
            isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Load))
            or type(node) in _BINARY or type(node) in _UNARY
            or (isinstance(node, ast.Constant) and isinstance(node.value, (int, float)))
            or (isinstance(node, ast.Name) and (node.id in VARIABLES or node.id in _FUNCTIONS))
            or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS
                and len(node.args) == 1 and not node.keywords)
        )
        if not allowed:
            raise ValueError(f"Disallowed syntax in pfd formula {formula!r}: {type(node).__name__}")
    return tree.body


def formula_variables(formula):
    return {node.id for node in ast.walk(_compile(formula)) if isinstance(node, ast.Name) and node.id in VARIABLES}


def _evaluate(node, values):
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values or values[node.id] is None:
            raise KeyError(node.id)
        return float(values[node.id])
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_evaluate(node.operand, values))
    if isinstance(node, ast.BinOp):
        return _BINARY[type(node.op)](_evaluate(node.left, values), _evaluate(node.right, values))
    if isinstance(node, ast.Call):
        return _FUNCTIONS[node.func.id](_evaluate(node.args[0], values))
    raise ValueError(f"Unsupported node {type(node).__name__}")


def evaluate_formula(formula, d, **parameters):
    return _evaluate(_compile(formula), {"d": d, **parameters})


@lru_cache(maxsize=1)
def load_criteria(path=CRITERIA_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def segment_at(criterion, elevation_deg):
    """Return the segment covering the angle; boundaries belong to the lower segment."""
    if not 0 <= elevation_deg <= 90:
        raise ValueError("Angle of arrival must be within 0-90 degrees")
    for segment in criterion["segments"]:
        if segment["elev_min_deg"] <= elevation_deg <= segment["elev_max_deg"]:
            return segment
    raise ValueError(f"No segment covers {elevation_deg} deg in {criterion['criterion_id']}")


def limit_at(criterion, elevation_deg, **parameters):
    """Evaluate a criterion at an angle of arrival.

    Returns a dict with the value in dB(W/m2) per reference bandwidth, or with
    ``value_db`` None and ``missing_parameters`` when X or Y is needed but unknown.
    """
    segment = segment_at(criterion, elevation_deg)
    needed = formula_variables(segment["formula"]) - {"d"}
    missing = sorted(name for name in needed if parameters.get(name) is None)
    value = None if missing else evaluate_formula(segment["formula"], elevation_deg, **parameters)
    return {
        "criterion_id": criterion["criterion_id"], "value_db": value,
        "unit": "dB(W/m2)", "reference_bandwidth_hz": criterion["reference_bandwidth_hz"],
        "elevation_deg": elevation_deg, "segment": segment, "missing_parameters": missing,
    }


def _inside_band(lower, upper, band):
    """True when the query shares spectrum with the band.

    An emission that only touches a band edge (e.g. ends at exactly 2 500 MHz) is not in
    that band: a positive-width query needs a positive-width overlap, and a single
    frequency must lie strictly inside the band.
    """
    if lower == upper:
        return band["frequency_min_hz"] < lower < band["frequency_max_hz"]
    return max(lower, band["frequency_min_hz"]) < min(upper, band["frequency_max_hz"])


def criteria_for(frequency_min_hz, frequency_max_hz, orbit=None, finland_only=True, document=None):
    """Return criteria whose bands intersect the closed satellite interval.

    ``orbit`` is "gso", "non_gso" or None (unknown: both are returned). Each result
    names the matched bands and whether the satellite band is fully inside them.
    When nothing applies the result is an explicit ``no_criterion`` record.
    """
    if orbit is not None and orbit not in ORBITS:
        raise ValueError(f"orbit must be one of {sorted(ORBITS)} or None")
    if frequency_min_hz > frequency_max_hz:
        raise ValueError("Inverted frequency interval")
    document = document or load_criteria()
    matches = []
    for criterion in document["criteria"]:
        if orbit is not None and criterion["orbit"] not in ("any", orbit):
            continue
        bands = [
            band for band in criterion["bands"]
            if _inside_band(frequency_min_hz, frequency_max_hz, band)
            and (band["applies_in_finland"] or not finland_only)
        ]
        if not bands:
            continue
        inside = any(
            band["frequency_min_hz"] <= frequency_min_hz and frequency_max_hz <= band["frequency_max_hz"] for band in bands
        )
        matches.append({
            "status": "criterion",
            "criterion_id": criterion["criterion_id"], "kind": criterion["kind"],
            "orbit": criterion["orbit"], "services": criterion["services"],
            "conditions": criterion["conditions"], "parameters": criterion["parameters"],
            "matched_bands": bands, "overlap": "inside" if inside else "partial",
            "provision": criterion["provision"], "location": criterion["location"],
            "source": criterion["source"],
        })
    if not matches:
        return [{
            "status": "no_criterion",
            "reason": "No Table 21-4 row applicable in Finland covers this frequency range"
                      + ("" if orbit is None else f" for orbit={orbit}") + ".",
            "frequency_min_hz": frequency_min_hz, "frequency_max_hz": frequency_max_hz,
        }]
    return matches


def criterion_by_id(criterion_id, document=None):
    document = document or load_criteria()
    for criterion in document["criteria"]:
        if criterion["criterion_id"] == criterion_id:
            return criterion
    raise KeyError(criterion_id)
