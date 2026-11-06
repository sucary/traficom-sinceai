from collections import Counter
import json
import re

from .manifest import json_default
from .specs import HEADERS, SHEET
from .stations import normalize_station, number


def extract_workbook(path, destination, dataset_id):
    from openpyxl import load_workbook

    book = load_workbook(path, read_only=True, data_only=False)
    cached_book = load_workbook(path, read_only=True, data_only=True)
    output = destination / "stations.jsonl"
    counts, station_ids, fingerprints = Counter(), Counter(), Counter()
    records = []
    formula_count = 0
    try:
        sheet = book[SHEET]
        cached_sheet = cached_book[SHEET]
        if sheet.cell(11, 1).value != "Station number" or sheet.cell(11, 9).value != "TX frequency":
            raise ValueError("Workbook header layout changed; inspect it before importing")
        raw_rows = sheet.iter_rows(min_row=13, max_col=22, values_only=True)
        cached_rows = cached_sheet.iter_rows(min_row=13, max_col=22, values_only=True)
        for row_number, (original_values, cached_values) in enumerate(zip(raw_rows, cached_rows, strict=True), 13):
            values = list(original_values)
            if all(value is None for value in values):
                continue
            if values[0] is None:
                raise ValueError(f"Nonempty workbook row {row_number} has no station number")
            formulas = {}
            for index, value in enumerate(values):
                if not isinstance(value, str) or not value.startswith("="):
                    continue
                references = re.fullmatch(r"=([A-Z]+\d+)(?:\+([A-Z]+\d+))?", value)
                if not references:
                    raise ValueError(f"Unsupported formula at row {row_number}: {value}")
                # Evaluate the workbook's references independently; never execute formula text as code.
                left = cached_sheet[references[1]].value
                expected = left if references[2] is None else number(left) + number(cached_sheet[references[2]].value)
                if cached_values[index] is None or expected != cached_values[index]:
                    raise ValueError(f"Missing or stale formula cache at row {row_number}: {value}")
                formulas[HEADERS[index]] = {"formula": value, "verified_value": expected}
                values[index] = expected
                formula_count += 1
            raw = dict(zip(HEADERS, values))
            record = normalize_station(raw, row_number, dataset_id)
            record["source_formulas"] = formulas
            station_ids[record["station_number"]] += 1
            fingerprint = json.dumps(raw, sort_keys=True, default=json_default)
            fingerprints[fingerprint] += 1
            records.append((record, fingerprint))
        with output.open("w", encoding="utf-8") as stream:
            for record, fingerprint in records:
                if station_ids[record["station_number"]] > 1:
                    record["quality_flags"].append("repeated_station_number")
                if fingerprints[fingerprint] > 1:
                    record["quality_flags"].append("duplicate_source_record")
                counts.update(record["quality_flags"])
                stream.write(json.dumps(record, ensure_ascii=False, default=json_default) + "\n")
    finally:
        book.close()
        cached_book.close()
    return {"records": len(records), "distinct_station_numbers": len(station_ids),
            "exact_duplicate_extra_rows": sum(count - 1 for count in fingerprints.values()),
            "quality_flags": dict(sorted(counts.items())), "verified_formulas": formula_count, "output": output.name,
            "notes": ["Original records retained; duplicate and invalid rows are not discarded or repaired.",
                      "Broad bounding box is a screening flag, not a country-boundary test.",
                      "Reported power is not assumed to be EIRP or ERP."]}
