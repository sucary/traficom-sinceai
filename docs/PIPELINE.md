# Pipeline, evidence and validation

`python -m app run <file>` is the entry point, one IFIC file per run. `ificNNNN.mdb`
runs the space pipeline and `brificNNNN.mdb` the terrestrial pipeline. Each issue is
written to `output/<file name>/`. The challenge requires `ific3074.mdb` and
`brific3076.mdb`. The space part is described below (`rebuild-analysis` is the same
space pipeline).

## Rebuild the analysis

`rebuild-analysis` rebuilds all default analysis directories from the four raw input
files. It first writes every stage to a clean staging directory. Before publishing
anything, it verifies that:

- frequency-match records equal the raw records consumed by case consolidation;
- consolidated cases equal the cases consumed by classification;
- the calculation queue equals the readiness cases; and
- readiness cases equal the number of PFD results.

Only a fully completed and validated generation replaces the default directories. The
run writes `analysis_pipeline_summary.json` in the issue folder with method versions, counts and the
cross-stage checks.

With the supplied inputs and the default one-bandwidth adjacent-channel screen, the
expected starting counts are 203,572 frequency matches: 136,613 co-frequency and 66,959
adjacent records. These consolidate to 20,512 review cases, of which 15,734 IFIC 3074
cases enter the PFD calculation.

## Self-contained final evidence

Every final JSONL PFD record contains the complete evidence needed for review without
joining back to intermediate files. It holds:

- source dataset IDs and SHA-256 hashes;
- notice and orbit source rows;
- the Finnish workbook identity and row;
- all considered frequency, group, emission and beam rows;
- a direct regulation citation with PDF page;
- a deterministic run ID with calculation parameters and hashes of every input artifact.

The CSV contains the key audit fields in flat columns. The run ID changes whenever an
input artifact, method version or calculation parameter changes.

## Independently validate the PFD calculations

```powershell
node backend\scripts\validate_pfd_independent.mjs output\ific3074
```

The validator does not import the production Python calculation. It independently
recalculates free-space geometry, PFD, Table 21-4 formulas, margins, classification
boundaries, and the worst non-GSO elevation with a finer search step. It reads
`<issue folder>/pfd-calculations/` (default `output/ific3074`) and writes
`<issue folder>/pfd-validation/independent_validation_summary.json`.

This validates the implementation, but it is not a comparison with ITU GIBC or a
Traficom-approved reference set. The screening deliberately assumes peak beam gain
towards every protected location and no adjacent-band attenuation, so a calculated
limit exceedance remains a reason for expert review, not proof of harmful interference
or a regulatory violation.

## Unit tests

```powershell
cd backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests/unit -t .
```
