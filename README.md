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

