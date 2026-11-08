import json
from pathlib import Path
import re
import shutil
import tempfile
import time

from ..config import PROJECT_ROOT
from ..ingestion.prepare import prepare
from . import (
    calculation_readiness,
    case_classification,
    case_consolidation,
    criteria_coverage,
    frequency_matching,
    pfd_calculation,
)


DEFAULT_IFIC = "ific3074.mdb"
WORKBOOK = "Traficom_SinceAI_Frequencies_of_interest_v05112026.xlsx"
REFERENCE_SNAPSHOTS = ("SPS_ALL_IFIC3083.mdb", "30B_3083.mdb")
SHARED_INPUTS = (*REFERENCE_SNAPSHOTS, WORKBOOK)
IFIC_FILE_PATTERN = re.compile(r"^ific(\d{4})\.mdb$", re.I)
REQUIRED_INPUTS = (DEFAULT_IFIC, *SHARED_INPUTS)


def required_inputs(ific_file=DEFAULT_IFIC):
    if not IFIC_FILE_PATTERN.fullmatch(ific_file):
        raise ValueError(f"Space IFIC file must be named ificNNNN.mdb, got {ific_file!r}")
    snapshots = tuple(name for name in REFERENCE_SNAPSHOTS if (PROJECT_ROOT / "data" / name).is_file())
    return (ific_file, *snapshots, WORKBOOK)
OUTPUT_DIRECTORIES = (
    "prepared",
    "frequency-matches",
    "frequency-cases",
    "classified-cases",
    "calculation-readiness",
    "pfd-criteria",
    "pfd-calculations",
)


def _copytree_with_retry(source, destination, attempts=10):
    for attempt in range(attempts):
        try:
            shutil.copytree(source, destination, dirs_exist_ok=True)
            return
        except (PermissionError, shutil.Error):
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)


def validate_counts(matches, cases, classified, readiness, pfd):
    checks = {
        "matches_to_cases": (
            matches["frequency_match_candidates"], cases["raw_match_candidates"]
        ),
        "cases_to_classification": (
            cases["review_cases"], classified["input_cases"]
        ),
        "queue_to_readiness": (
            classified["future_calculation_queue"], readiness["input_cases"]
        ),
        "readiness_to_pfd": (
            readiness["input_cases"], sum(pfd["counts"].values())
        ),
    }
    failures = {name: values for name, values in checks.items() if values[0] != values[1]}
    if failures:
        detail = ", ".join(f"{name}: {left} != {right}" for name, (left, right) in failures.items())
        raise ValueError(f"Analysis pipeline count validation failed: {detail}")
    return {name: {"upstream": left, "downstream": right, "matches": True}
            for name, (left, right) in checks.items()}


def _publish(stage_root, output_root):
    backup_root = stage_root / ".previous"
    backup_root.mkdir()
    backed_up = []
    published = []
    try:
        for name in OUTPUT_DIRECTORIES:
            target = output_root / name
            if target.exists():
                _copytree_with_retry(target, backup_root / name)
                backed_up.append(name)
        for name in OUTPUT_DIRECTORIES:
            _copytree_with_retry(stage_root / name, output_root / name)
            published.append(name)
    except Exception:
        for name in reversed(backed_up):
            _copytree_with_retry(backup_root / name, output_root / name)
        raise


def run(output_root, near_margin_db=pfd_calculation.DEFAULT_NEAR_MARGIN_DB, ific_file=DEFAULT_IFIC):
    inputs = required_inputs(ific_file)
    if missing := [name for name in inputs if not (PROJECT_ROOT / "data" / name).is_file()]:
        raise ValueError(f"Missing input files in data/: {missing}")
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=".analysis-rebuild-", dir=output_root))
    try:
        prepared = prepare(PROJECT_ROOT, stage_root / "prepared", only=inputs)
        if not prepared["complete"]:
            raise ValueError("Input preparation failed")

        matches = frequency_matching.run(
            stage_root / "prepared", stage_root / "frequency-matches",
            adjacent_channels=frequency_matching.DEFAULT_ADJACENT_CHANNELS,
        )
        cases = case_consolidation.run(
            stage_root / "frequency-matches" / "frequency_match_candidates.jsonl",
            stage_root / "frequency-cases",
        )
        classified = case_classification.run(
            stage_root / "frequency-cases" / "frequency_review_cases.jsonl",
            stage_root / "classified-cases",
        )
        readiness = calculation_readiness.run(
            stage_root / "prepared",
            stage_root / "classified-cases" / "future_calculation_queue.jsonl",
            stage_root / "calculation-readiness",
        )
        criteria = criteria_coverage.run(
            stage_root / "frequency-cases" / "frequency_review_cases.jsonl",
            stage_root / "pfd-criteria",
        )
        pfd = pfd_calculation.run(
            stage_root / "calculation-readiness",
            stage_root / "frequency-cases" / "frequency_review_cases.jsonl",
            stage_root / "pfd-calculations",
            near_margin_db,
        )
        checks = validate_counts(matches, cases, classified, readiness, pfd)
        summary = {
            "schema_version": 1,
            "status": "completed_and_validated",
            "evaluated_ific": ific_file,
            "inputs": list(inputs),
            "reference_snapshots_missing": [n for n in REFERENCE_SNAPSHOTS if n not in inputs],
            "adjacent_channels": frequency_matching.DEFAULT_ADJACENT_CHANNELS,
            "method_versions": {
                "frequency_matching": matches["method_version"],
                "case_consolidation": cases["method_version"],
                "case_classification": classified["method_version"],
                "calculation_readiness": readiness["method_version"],
                "criteria_coverage": criteria["method_version"],
                "pfd_calculation": pfd["method_version"],
            },
            "counts": {
                "frequency_match_candidates": matches["frequency_match_candidates"],
                "frequency_matches_by_relation": matches["candidates_by_relation"],
                "review_cases": cases["review_cases"],
                "calculation_queue": classified["future_calculation_queue"],
                "pfd_results": sum(pfd["counts"].values()),
            },
            "pfd_run_id": pfd["run"]["run_id"],
            "cross_stage_checks": checks,
        }
        (stage_root / "analysis_pipeline_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        _publish(stage_root, output_root)
        shutil.copy2(stage_root / "analysis_pipeline_summary.json", output_root / "analysis_pipeline_summary.json")
        return summary
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
