# Traficom SinceAI risk assessment

The backend prepares the supplied Finnish frequency data and space IFIC databases,
finds co-frequency and adjacent-frequency cases, and calculates worst-case PFD
margins for expert review.

It also contains a separate terrestrial land-mobile workflow for consecutive
BR IFIC issues 3075/3076, ECC T/R 25-08 criteria and ITU-R P.1546-6 field-strength
screening. See `docs/TERRESTRIAL_ANALYSIS.md`.

## Rebuild the analysis

Run the complete pipeline with one command from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app rebuild-analysis
```

The command rebuilds all default analysis directories from the four raw input files.
It first writes every stage to a clean staging directory. Before publishing anything,
it verifies that:

- frequency-match records equal the raw records consumed by case consolidation;
- consolidated cases equal the cases consumed by classification;
- the calculation queue equals the readiness cases; and
- readiness cases equal the number of PFD results.

Only a fully completed and validated generation replaces the default directories.
The run writes `output/analysis_pipeline_summary.json` with method versions, counts,
and the cross-stage checks.

With the supplied inputs and the default one-bandwidth adjacent-channel screen, the
expected starting counts are 203,572 frequency matches: 136,613 co-frequency and
66,959 adjacent records. These consolidate to 20,512 review cases, of which 15,734
IFIC 3074 cases enter the PFD calculation.

## Self-contained final evidence

Every final JSONL PFD record contains the complete evidence needed for review without
joining back to intermediate files: source dataset IDs and SHA-256 hashes, notice and
orbit source rows, Finnish workbook identity and row, all considered frequency/group/
emission/beam rows, direct regulation citation and PDF page, and a deterministic run
ID with calculation parameters and hashes of every input artifact. The CSV contains
the key audit fields in flat columns. The run ID changes whenever an input artifact,
method version, or calculation parameter changes.

## Independently validate the PFD calculations

Run the separate JavaScript validator from the repository root:

```powershell
node backend/scripts/validate_pfd_independent.mjs
```

It does not import the production Python calculation. It independently recalculates
free-space geometry, PFD, Table 21-4 formulas, margins, classification boundaries,
and the worst non-GSO elevation with a finer search step. Its result is written to
`output/pfd-validation/independent_validation_summary.json`.

This validates the implementation, but it is not a comparison with ITU GIBC or a
Traficom-approved reference set. Because the screening deliberately assumes peak beam
gain towards every protected location and no adjacent-band attenuation, a calculated
limit exceedance remains a reason for expert review—not proof of harmful interference
or a regulatory violation.

## AI handoff: which outputs to read

Results are generated locally and are not in git (`output/` is ignored). Run the
pipelines first (`rebuild-analysis`, `analyze-terrestrial`). Records with the same
`run_id` come from identical inputs, code version and parameters.

**Space, IFIC 3074** (`output/pfd-calculations/`; other issues: `output/ificNNNN/pfd-calculations/`)

| File | Use |
| --- | --- |
| `case_pfd_results.jsonl` | One self-contained record per case: Finnish station × satellite notice × protected band. The main AI input. |
| `case_pfd_results.csv` | The same cases as flat columns, for tables and quick filtering. |
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
  are in `docs/` (same SHA-256 as `docs/reference/itu-rr-2024/`). Table 21-4
  footnote texts are in `backend/src/app/reference/pfd_criteria.json` (`footnotes`).
- Provenance: `evidence` (source datasets, hashes, source rows), `run`, `assumptions`.

Typical selection for review: `result.status` in `exceeds_limit`, `near_limit`,
`unallocated_service_rr_4_4`, grouped by `space.notice_id` (one notice = one
correspondence unit).

**Terrestrial, IFIC 3076** (`output/terrestrial-ific3076/`)

| File | Use |
| --- | --- |
| `terrestrial_ific3076_findings.jsonl` / `.csv` | Calculated P.1546 findings: `result` (`exceeds_threshold`, `near_threshold`, `below_threshold`), `administration`, `frequency_mhz`, `distance_km`, `field_strength_dbuv_m`, `threshold_dbuv_m`, `margin_db`, `assessments`, `source_notice`, `criterion`, `model`, `sources`. |
| `terrestrial_ific3076_screening.jsonl` | All screened events, including those beyond P.1546's 1 000 km range. |
| `terrestrial_trends.json`, `terrestrial_summary.json` | Issue-to-issue trends; counts, assumptions, run ID. |

Known limitation: the border geometry is the generalised GISCO coastline, not the outer
limit of Finland's territorial sea (12 nautical miles), which Traficom asked to be
assessed. Sea-path distances may therefore be too long, and field strengths too low.

**Interpretation rules for generated text:** every result is a deterministic,
pessimistic screening value (peak beam gain towards every station). An exceedance is a
reason for expert review, not proof of harmful interference or a regulatory violation.
Explanations should quote the numbers, status and citations from the record rather than
recompute them. Method details: `docs/PFD_CALCULATION.md`, `docs/PFD_CRITERIA.md`,
`docs/TERRESTRIAL_ANALYSIS.md`.

