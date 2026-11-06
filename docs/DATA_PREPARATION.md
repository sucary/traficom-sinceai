# Local data preparation results

Prepared on 6 November 2026 using the files currently in this checkout.
These are extraction results, not interference findings.

| Input | Selected tables exported | Source records |
| --- | ---: | ---: |
| Space IFIC 3074 | 11 | 457,440 |
| Terrestrial IFIC 3076 | 10 | 21,715 |
| AP30/30A snapshot 3083 | 11 | 377,731 |
| AP30B snapshot 3083 | 11 | 44,273 |
| Synthetic frequency workbook | 1 worksheet | 874 |
| Total | 43 MDB tables and 1 worksheet | 902,033 |

The preparation manifest includes SHA-256 checksums for all nine original files,
the full non-system MDB table catalogues, exported column names and record counts.
Generated exports and the manifest are under `output/prepared/`, excluded from Git.
The four reference documents were inventoried; their text/tables were not extracted.

## Workbook quality

There are 874 records and 872 distinct station numbers. Two station numbers occur
twice. One repeated record is an exact duplicate. All rows are retained with their
original worksheet row numbers.

The workbook contains 29 formulas: direct cell references and additions. Their saved
results were verified independently against the referenced cells before import.

| Flag | Affected rows |
| --- | ---: |
| Missing receive frequency | 61 |
| Missing transmit frequency | 3 |
| Missing channel bandwidth | 2 |
| Missing or unsupported reported power | 345 |
| Directional antenna without direction | 50 |
| Inconsistent antenna heights | 4 |
| Antenna ASL below ground | 1 |
| Antenna below 1 metre AGL | 1 |
| Repeated station number | 4 |
| Exact duplicate source record | 2 |

Flags can overlap. The power flag comprises 342 missing values and three mW values
not yet normalized; W and kW are normalized. Power reference codes remain preserved;
reported power is not assumed to be ERP/EIRP. Missing RX frequency does not invalidate
a transmitter record; downstream analysis must decide which records apply.

## Remaining work

- Reconcile MDB extraction against an independent reader before relying on completeness.
- Validate ITU joins, field units and notice status codes using the SNS/TerRaSys definitions.
- Build normalized notice and assignment tables from the staging records.
- Extract the M4 allocation table from an authoritative structured source.
- Connect the loader to Aiven once its connection configuration is available.
- Add deterministic candidate matching and expert-reviewable findings.

Snapshot 3083 is kept distinct from evaluation issue 3074. The terrestrial input
currently contains issue 3076 only, so consecutive-issue comparison is not available.
