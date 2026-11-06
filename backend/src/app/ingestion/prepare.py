import re

from .access import extract_mdb
from .manifest import sha256, write_json
from .specs import SYNTHETIC_WORKBOOK
from .workbook import extract_workbook


def prepare(root, output, catalog_only=False, only=None):
    manifest = {"version": 1, "complete": False, "datasets": [], "errors": []}
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted(path for folder in (root / "data", root / "docs") for path in folder.iterdir()
                   if path.is_file() and path.suffix.lower() in {".mdb", ".xlsx", ".pdf", ".docx"}
                   and not path.name.startswith(".env") and (not only or path.name in only))
    if not paths:
        raise ValueError("No supported input files matched")
    for path in paths:
        print(f"Preparing {path.name}", flush=True)
        digest = sha256(path)
        item = {"file": path.relative_to(root).as_posix(), "sha256": digest,
                "dataset_id": digest, "bytes": path.stat().st_size,
                "issue": int(match[0]) if (match := re.findall(r"\d{4}", path.stem)) and path.suffix == ".mdb" else None,
                "is_synthetic": path.name == SYNTHETIC_WORKBOOK, "status": "inventoried"}
        manifest["datasets"].append(item)
        destination = output / path.stem / digest[:12]
        destination.mkdir(parents=True, exist_ok=True)
        try:
            if path.suffix == ".xlsx":
                if path.name != SYNTHETIC_WORKBOOK:
                    raise ValueError("Unknown workbook: define its layout and synthetic/real classification before importing")
                item["extraction"] = extract_workbook(path, destination, digest)
                item["status"] = "extracted"
            elif path.suffix == ".mdb":
                item["extraction"] = extract_mdb(path, destination, digest, catalog_only)
                item["status"] = "catalogued" if catalog_only else "extracted"
            item["output_directory"] = destination.relative_to(output).as_posix()
        except Exception as error:
            item["status"] = "failed"
            item["error"] = f"{type(error).__name__}: {error}"
            manifest["errors"].append({"file": item["file"], "error": item["error"]})
        write_json(output / "manifest.json", manifest)
    manifest["complete"] = not manifest["errors"]
    write_json(output / "manifest.json", manifest)
    return manifest
