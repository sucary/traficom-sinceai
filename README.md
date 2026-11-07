# Traficom SinceAI risk assessment

The backend prepares the supplied Finnish frequency data and space IFIC databases,
finds co-frequency and adjacent-frequency cases, and calculates worst-case PFD
margins for expert review.

## Run the calculation

Before you start:

1. Put the input files in the `data` folder: the ITU databases (`ific3074.mdb`,
   `SPS_ALL_IFIC3083.mdb`, `30B_3083.mdb`, `brific3075.mdb`, `brific3076.mdb`) and the
   Traficom Excel file. The databases are too large for git, so download them separately.
2. Open a terminal in the project folder (the folder that contains this README).
3. Close any existing Excel file in project.

Then run the same command once per IFIC file, changing only the file name:

```
.venv\Scripts\python.exe -m app run <file>
```

The challenge requires two files. Each gets its own results folder:

| File | Run | Results |
| --- | --- | --- |
| Space IFIC 3074 | `.venv\Scripts\python.exe -m app run ific3074.mdb` | `output\ific3074\` |
| Terrestrial IFIC 3076 | `.venv\Scripts\python.exe -m app run brific3076.mdb` | `output\brific3076\` |

A file name starting with `ific` runs the space calculation. One starting with `brific` runs the terrestrial calculation, which also needs the previous issue in `data` (for 3076, that is `brific3075.mdb`). More detail: `docs/PIPELINE.md`.

## Print AI explanations for flagged results

After both assessment runs have generated their output folders, run this from the
project root:

```powershell
.\.venv\Scripts\python.exe backend\scripts\explain_risks.py
```

The script prints model explanations for the three highest-priority satellite notices
and terrestrial threshold exceedances, along with the evidence used. Use `--limit 5`
to show up to five of each. It reads the generated JSONL locally, but sends each
selected evidence summary to the model API configured by `OPENCODE_API_URL`,
`OPENCODE_API_KEY`, and `OPENCODE_MODEL` in `.env`. Use `--show-evidence` to also print
the evidence sent to the model. An explanation is a screening aid, not proof of harmful
interference or a regulatory violation.

## AI handoff: which outputs to read

Results are generated locally and are not in git (`output/` is ignored). Records with
the same `run_id` come from identical inputs, code version and parameters.

**Space, IFIC 3074** (`output/ific3074/pfd-calculations/`)

| File | Use |
| --- | --- |
| `case_pfd_results.jsonl` | One self-contained record per case: Finnish station × satellite notice × protected band. The main AI input. |
| `case_pfd_results.csv` | The same cases as flat columns. |
| `pfd_summary.json` | Counts per status, assumptions, and `status_definitions`, the authoritative meaning of every status. |

Key fields in a JSONL record:

- Who and what: `space.administration` (ITU code), `space.notice_id`, `satellite_names`,
  `space.provision` (9.1/IA = API, 9.6 = CR/C, 11.2 = notification, RS49), `space.action_code`,
  `space.notice_publication_issue`, `space.publication_date`.
- Finnish side: `finnish_station` (station number, coordinates, protected band).
- Verdict: `result.status`, `result.worst_margin_db` (negative = above the limit),
  `result.pfd_db`, `result.limit_db`, `result.reference_bandwidth_hz`,
  `result.worst_elevation_deg`, `result.governing_criterion_id`,
  `result.national_context_m4`, and `result.rr_4_4_unallocated_rows` when present.
- Reasoning: `evaluations[]`, one per Table 21-4 row considered, with `service`,
  `conditions`, `sharing` (Article 5 Region 1 and M4 checks), `applicability`, `caveats`
  and `emission`.
- Citations: `result.regulation_citation` (document, provision, printed and PDF page,
  file SHA-256), plus Article 5 page locations in `evaluations[].sharing`. The RR PDFs
  are in `data/` (same SHA-256 as `docs/reference/itu-rr-2024/`). Table 21-4 footnote texts are in
  `backend/src/app/reference/pfd_criteria.json` (`footnotes`).
- Provenance: `evidence` (source datasets, hashes, source rows), `run`, `assumptions`.

Typical selection for review: `result.status` in `exceeds_limit`, `near_limit`,
`unallocated_service_rr_4_4`, grouped by `space.notice_id` (one notice = one
correspondence unit).

**Terrestrial, IFIC 3076** (`output/brific3076/`)

| File | Use |
| --- | --- |
| `terrestrial_ific3076_findings.jsonl` / `.csv` | Calculated P.1546 findings: `result` (`exceeds_threshold`, `near_threshold`, `below_threshold`), `administration`, `frequency_mhz`, `distance_km`, `field_strength_dbuv_m`, `threshold_dbuv_m`, `margin_db`, `assessments`, `source_notice`, `criterion`, `model`, `sources`. |
| `terrestrial_ific3076_screening.jsonl` | All screened events, including those beyond P.1546's 1 000 km range. |
| `terrestrial_trends.json`, `terrestrial_summary.json` | Issue-to-issue trends; counts, assumptions, run ID. |

Known limitation: the border geometry is the generalised GISCO coastline, not the outer
limit of Finland's territorial sea (12 nautical miles). Sea-path distances may therefore
be too long, and field strengths too low.

**Interpretation rules for generated text:** every result is a deterministic,
pessimistic screening value (peak beam gain towards every station). An exceedance is a
reason for expert review, not proof of harmful interference or a regulatory violation.
Explanations should quote the numbers, status and citations from the record rather than
recompute them. Method details: `docs/PFD_CALCULATION.md`, `docs/PFD_CRITERIA.md`,
`docs/TERRESTRIAL_ANALYSIS.md`.
