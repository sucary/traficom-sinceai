import json

from .manifest import json_default
from .specs import SPACE_TABLES, TERRESTRIAL_TABLES


def extract_mdb(path, destination, dataset_id, catalog_only=False):
    from access_parser import AccessParser

    database = AccessParser(str(path))
    catalog = sorted(name for name in database.catalog if not name.startswith("MSys"))
    # Filename conventions vary between the downloadable extract, DVD and user
    # copies.  The table catalogue is authoritative; a terrestrial extract is
    # identified by its FXM primary table rather than by a fragile name prefix.
    selected = TERRESTRIAL_TABLES if "fxm_terra" in catalog else SPACE_TABLES
    result = {"catalog": catalog, "tables": {}, "scope": "catalog_only" if catalog_only else "selected_tables",
              "notes": ["Raw values only; ITU units and relationships must be validated before analysis.",
                        "Source row is extraction order, not an ITU notice identifier.",
                        "Parser output is provisional until reconciled against an independent reader."]}
    if catalog_only:
        return result
    for table_name in selected:
        if table_name not in catalog:
            raise ValueError(f"Required extraction table {table_name!r} absent in {path.name}")
        print(f"Extracting {path.name}/{table_name}", flush=True)
        table = database.parse_table(table_name)
        columns = list(table)
        lengths = {len(table[column]) for column in columns}
        if len(lengths) > 1:
            raise ValueError(f"Unequal column lengths in {path.name}/{table_name}")
        row_count = next(iter(lengths), 0)
        output = destination / f"{table_name}.jsonl"
        temp_output = output.with_suffix(".tmp")
        with temp_output.open("w", encoding="utf-8") as stream:
            for index in range(row_count):
                record = {"dataset_id": dataset_id, "source_table": table_name, "source_row": index + 1,
                          "raw": {column: table[column][index] for column in columns}}
                stream.write(json.dumps(record, ensure_ascii=False, default=json_default) + "\n")
        temp_output.replace(output)
        result["tables"][table_name] = {"columns": columns, "records": row_count, "output": output.name}
    return result
