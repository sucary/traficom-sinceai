"""One command for any IFIC file: the file name decides which pipeline runs.

- ``ificNNNN.mdb``   -> Space IFIC: frequency matching through worst-case PFD verdicts.
- ``brificNNNN.mdb`` -> Terrestrial BR IFIC: compared with issue NNNN-1 (which must
  also be in ``data/``), P.1546 field strengths against ECC T/R 25-08.

One file per run; each issue is written to its own folder,
``output/<file name without .mdb>/``, because each publication is evaluated and
reviewed separately. The challenge requires ``ific3074.mdb`` and ``brific3076.mdb``.
"""

from pathlib import Path
import re

from ..config import PROJECT_ROOT
from ..ingestion.prepare import prepare
from ..ingestion.specs import SYNTHETIC_WORKBOOK
from . import pipeline, terrestrial_pipeline


SPACE = re.compile(r"^ific(\d{4})\.mdb$", re.I)
TERRESTRIAL = re.compile(r"^brific(\d{4})\.mdb$", re.I)


def plan(file_name):
    """Return (kind, issue, input files) for one IFIC file name, or raise ValueError."""
    if match := SPACE.fullmatch(file_name):
        return "space", int(match[1]), pipeline.required_inputs(file_name)
    if match := TERRESTRIAL.fullmatch(file_name):
        issue = int(match[1])
        return "terrestrial", issue, (f"brific{issue - 1}.mdb", file_name, SYNTHETIC_WORKBOOK)
    raise ValueError(f"Not an IFIC file name (expected ificNNNN.mdb or brificNNNN.mdb): {file_name!r}")


def run_one(file_name, output_root):
    kind, issue, inputs = plan(file_name)
    if missing := [name for name in inputs if not (PROJECT_ROOT / "data" / name).is_file()]:
        raise ValueError(f"{file_name}: missing input files in data/: {missing}")
    target = output_root / Path(file_name).stem.lower()
    if kind == "space":
        summary = pipeline.run(target, ific_file=file_name)
        return {"file": file_name, "kind": kind, "issue": issue, "output": str(target),
                "status": summary["status"], "counts": summary["counts"]}
    prepared = prepare(PROJECT_ROOT, target / "prepared", only=inputs)
    if not prepared["complete"]:
        raise ValueError(f"{file_name}: input preparation failed: {prepared['errors']}")
    summary = terrestrial_pipeline.run(target / "prepared", target, current_issue=issue)
    return {"file": file_name, "kind": kind, "issue": issue, "output": str(target),
            "status": summary["status"], "counts": summary["counts"]}


def run(file_name, output_root=None):
    plan(file_name)  # reject a wrong name before any long work starts
    return run_one(file_name, (output_root or PROJECT_ROOT / "output").resolve())
