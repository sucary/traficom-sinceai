import json
from pathlib import Path
from tempfile import TemporaryDirectory

from support import local_connection

from app.db.loader import load
from app.db.migrations import migrate
from app.config import PROJECT_ROOT


def main():
    prepared = (PROJECT_ROOT / "output/prepared")
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    expected_raw = sum(
        extraction.get("records", 0) + sum(table["records"] for table in extraction.get("tables", {}).values())
        for dataset in manifest["datasets"] for extraction in [dataset.get("extraction", {})]
    )
    with local_connection() as connection:
        migrate(connection)
        first = load(connection, prepared)
        assert first["source_rows"] == expected_raw, (first, expected_raw)
        second = load(connection, prepared)
        assert first == second
        actual = connection.execute("SELECT count(*) FROM ingestion.source_rows").fetchone()[0]
        assert actual == expected_raw, (actual, expected_raw)
        assert connection.execute("SELECT count(*) FROM ingestion.stations").fetchone()[0] == first["stations"]
        dataset = next(d for d in manifest["datasets"] if d["file"].endswith(".xlsx"))
        with TemporaryDirectory(dir=PROJECT_ROOT / "output") as temporary:
            test_root = Path(temporary)
            test_dataset = json.loads(json.dumps(dataset))
            test_dataset["output_directory"] = "fixture"
            fixture = test_root / "fixture"
            fixture.mkdir()
            original = prepared / dataset["output_directory"] / dataset["extraction"]["output"]
            (fixture / dataset["extraction"]["output"]).write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
            test_dataset["extraction"]["records"] += 1
            (test_root / "manifest.json").write_text(json.dumps({"complete": True, "errors": [], "datasets": [test_dataset]}))
            try:
                load(connection, test_root)
            except ValueError:
                pass
            else:
                raise AssertionError("Mismatched export was not rejected")
        assert connection.execute("SELECT count(*) FROM ingestion.source_rows").fetchone()[0] == expected_raw
        assert connection.execute("SELECT count(*) FROM ingestion.stations").fetchone()[0] == first["stations"]
        print(json.dumps({"passed": True, "source_rows": actual, "stations": first["stations"],
                          "checks": ["full import", "duplicate-free reimport", "row-count rejection", "rollback preserves previous data"]}))


if __name__ == "__main__":
    main()
