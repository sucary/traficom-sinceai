import json

from psycopg.types.json import Jsonb


def checked_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Prepared output path escapes its directory")
    return path


def load(connection, prepared):
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete") or manifest.get("errors"):
        raise ValueError("Preparation is incomplete; resolve its errors before loading")
    if any(dataset["status"] == "catalogued" for dataset in manifest["datasets"]):
        raise ValueError("Catalogue-only output cannot be loaded; extract the selected tables first")
    totals = {"source_rows": 0, "stations": 0}
    with connection.transaction():
        for dataset in manifest["datasets"]:
            connection.execute(
                "INSERT INTO ingestion.datasets(dataset_id,file_name,issue,is_synthetic,metadata) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT(dataset_id) DO UPDATE SET metadata=excluded.metadata",
                (dataset["dataset_id"], dataset["file"], dataset["issue"], dataset["is_synthetic"], Jsonb(dataset)),
            )
            if dataset["status"] != "extracted":
                continue
            destination = checked_path(prepared, dataset["output_directory"])
            extraction = dataset["extraction"]
            is_workbook = "output" in extraction
            tables = [("Frequencies of interest", extraction)] if is_workbook else list(extraction["tables"].items())
            for table_name, metadata in tables:
                source = checked_path(destination, metadata["output"])
                if is_workbook:
                    connection.execute("DELETE FROM ingestion.stations WHERE dataset_id=%s", (dataset["dataset_id"],))
                connection.execute("DELETE FROM ingestion.source_rows WHERE dataset_id=%s AND source_table=%s",
                                   (dataset["dataset_id"], table_name))
                count = 0
                with source.open(encoding="utf-8") as stream, connection.cursor() as cursor:
                    with cursor.copy("COPY ingestion.source_rows(dataset_id,source_table,source_row,payload) FROM STDIN") as copy:
                        for line in stream:
                            row = json.loads(line)
                            if row["dataset_id"] != dataset["dataset_id"] or row["source_table"] != table_name:
                                raise ValueError("Export provenance does not match manifest")
                            copy.write_row((row["dataset_id"], row["source_table"], row["source_row"], Jsonb(row["raw"])))
                            count += 1
                if count != metadata["records"]:
                    raise ValueError(f"Export row count differs from manifest for {table_name}")
                totals["source_rows"] += count
                if is_workbook:
                    with source.open(encoding="utf-8") as stream, connection.cursor() as cursor:
                        with cursor.copy(
                            "COPY ingestion.stations(dataset_id,source_table,source_row,station_number,"
                            "tx_frequency_hz,rx_frequency_hz,channel_bandwidth_hz,longitude,latitude,quality_flags,normalized) FROM STDIN"
                        ) as copy:
                            for line in stream:
                                row = json.loads(line)
                                copy.write_row((row["dataset_id"], row["source_table"], row["source_row"], row["station_number"],
                                                row["tx_frequency_hz"], row["rx_frequency_hz"], row["channel_bandwidth_hz"],
                                                row["longitude"], row["latitude"], Jsonb(row["quality_flags"]), Jsonb(row)))
                                totals["stations"] += 1
    return totals
