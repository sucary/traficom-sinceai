# Querying the shared database

The `ingestion` schema preserves imported source values. The `core` schema provides
typed views, which are saved queries over those values. The `analysis` schema stores
future analysis runs and evidence. Creating these objects does not generate findings.

## Apply the migration

In Git Bash, from the repository root:

```bash
./.venv/Scripts/python.exe -m app migrate --host traficom-clewdr.i.aivencloud.com --port 28339 --database defaultdb --user avnadmin --ca certs/ca.pem
```

Enter the password at the hidden prompt. This operation creates or updates views and
creates empty analysis tables. It does not reimport, delete or modify source records.
It can be rerun. Migration names and checksums are tracked in
`ingestion.schema_migrations`; only pending SQL files are applied. Existing databases
are adopted by reapplying the original idempotent SQL once. Source data is preserved.
No `.env` files are read. Install the package first with `python -m pip install -e ./backend`.

## Available views

| View in `core` | Contents |
| --- | --- |
| `source_records` | Original JSON with source file and snapshot issue |
| `space_notices` | Notice IDs, administrations, dates, publication codes |
| `space_groups` | Group-to-notice relationships and beam direction codes |
| `space_frequencies` | Frequency ranges and bandwidths normalized to Hz |
| `space_frequency_notices` | Frequencies joined to notices within the same dataset |
| `space_assignments` | Assigned frequency entries normalized to Hz |
| `space_emissions` | Emission designators and original power values |
| `space_geo_satellites` | Satellite names and nominal orbital longitude |
| `space_non_geo_satellites` | Satellite names, plane counts and reference body codes |
| `terrestrial_assignments` | FXM assignment IDs, administrations, class/status codes |
| `protected_stations` | Normalized workbook records with quality flags |

IDs are PostgreSQL bigints, measured frequencies are numeric, and dates are SQL dates.
Invalid typed values become NULL; original values remain in `ingestion.source_rows.payload`.
Compare with the raw value when distinguishing missing input from malformed input.
No source status or regulatory codes are silently interpreted.

The [ITU SNS Preface, May 2026](https://www.itu.int/en/ITU-R/space/Preface/preface_e.pdf)
defines `freq_mhz`, `freq_min`, and `freq_max` in MHz, `bdwdth` in kHz, and `emi_rcp`
as E for emission or R for reception. Frequency views multiply the corresponding
source units to obtain Hz. They use `freq_mhz`, rather than assuming `freq_assgn`
always has MHz units. Terrestrial frequency and bandwidth fields remain explicitly
labelled `_source` until their units are validated. Emission power fields remain
unconverted; no ERP/EIRP interpretation is applied.

## Example queries

```sql
SELECT notice_id, administration, notice_type, publication_date
FROM core.space_notices
WHERE dataset_issue = 3074
ORDER BY notice_id;

SELECT notice_id, administration, group_id, emission_reception_code,
       frequency_min_hz, frequency_max_hz, bandwidth_hz
FROM core.space_frequency_notices
WHERE dataset_issue = 3074
ORDER BY notice_id, group_id, sequence_number
LIMIT 100;

SELECT station_number, rx_frequency_hz, channel_bandwidth_hz, quality_flags
FROM core.protected_stations
ORDER BY source_row;
```

`dataset_issue` identifies the snapshot file; `publication_issue` identifies the
publication attached to a source notice or frequency record. These can differ.
Always include `dataset_id` when joining records. IDs can recur in other snapshots.

The current local export has unique notice IDs and group IDs within each space
dataset. Every exported frequency links to a group and every group to a notice.
This does not establish that the original MDB extraction was complete.

## Saved findings

- `analysis.runs`: method/version, parameters, assumptions and execution status.
- `analysis.run_datasets`: exact source dataset hashes and their roles in each run.
- `analysis.findings`: candidates, explanations, frequency ranges, calculation inputs/results,
  missing information and expert review status.
- `analysis.finding_evidence`: links findings to original source rows.

Evidence must refer to a dataset explicitly selected for that run, and to an existing
source row. Frequency endpoints must be paired and ordered. A finding key is unique
within a run so the same candidate cannot accidentally be inserted twice.

These tables start empty. A frequency overlap is a candidate for review, not proof
of harmful interference. Regulatory citations can be stored in the finding's calculation
JSON until a dedicated regulation/citation model is introduced.
