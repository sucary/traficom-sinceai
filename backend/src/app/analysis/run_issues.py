import json
from pathlib import Path
import re

from ..config import PROJECT_ROOT
from ..ingestion.prepare import prepare
from ..ingestion.specs import SYNTHETIC_WORKBOOK
from . import pipeline, terrestrial_pipeline


SPACE = re.compile(r"^ific(\d{4})\.mdb$", re.I)
TERRESTRIAL = re.compile(r"^brific(\d{4})\.mdb$", re.I)


def plan(file_name):
    if match := SPACE.fullmatch(file_name):
        return "space", int(match[1]), pipeline.required_inputs(file_name)
    if match := TERRESTRIAL.fullmatch(file_name):
        issue = int(match[1])
        previous = f"brific{issue - 1}.mdb"
        inputs = (previous,) if (PROJECT_ROOT / "data" / previous).is_file() else ()
        return "terrestrial", issue, (*inputs, file_name, SYNTHETIC_WORKBOOK)
    raise ValueError(f"Not an IFIC file name (expected ificNNNN.mdb or brificNNNN.mdb): {file_name!r}")


def run_one(file_name, output_root):
    kind, issue, inputs = plan(file_name)
    if missing := [name for name in inputs if not (PROJECT_ROOT / "data" / name).is_file()]:
        raise ValueError(f"{file_name}: missing input files in data/: {missing}")
    target = output_root / Path(file_name).stem.lower()
    if kind == "space":
        summary = pipeline.run(target, ific_file=file_name)
        pfd = json.loads((target / "pfd-calculations" / "pfd_summary.json").read_text(encoding="utf-8"))
        return {"file": file_name, "kind": kind, "issue": issue, "output": str(target),
                "status": summary["status"], "counts": pfd["counts"]}
    prepared = prepare(PROJECT_ROOT, target / "prepared", only=inputs)
    if not prepared["complete"]:
        raise ValueError(f"{file_name}: input preparation failed: {prepared['errors']}")
    summary = terrestrial_pipeline.run(target / "prepared", target, current_issue=issue)
    return {"file": file_name, "kind": kind, "issue": issue, "output": str(target),
            "status": summary["status"], "counts": summary["counts"]}


def run(file_name, output_root=None):
    plan(file_name)
    return run_one(file_name, (output_root or PROJECT_ROOT / "output").resolve())


def issue_order(file_name):
    kind, issue, _ = plan(file_name)
    return (kind, issue)


def run_many(file_names, output_root=None, on_progress=None):
    results = []
    for name in sorted(file_names, key=issue_order):
        if on_progress:
            on_progress(name, "running", None)
        try:
            result = run(name, output_root)
        except Exception as error:
            result = {"file": name, "status": "failed", "error": str(error)}
        results.append(result)
        if on_progress:
            on_progress(name, result["status"], result)
    return results
