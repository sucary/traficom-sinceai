# Terrestrial IFIC 3076 analysis

The terrestrial workflow implements the challenge's land-mobile side quest as a
separate deterministic path. It does not reuse satellite PFD logic.

## Rebuild

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m app prepare --root . --output output\terrestrial-prepared `
  --only brific3075.mdb --only brific3076.mdb `
  --only Traficom_SinceAI_Frequencies_of_interest_v05112026.xlsx
.\.venv\Scripts\python.exe -m app analyze-terrestrial `
  --prepared output\terrestrial-prepared `
  --output output\terrestrial-ific3076 --issue 3076
```

The first command extracts issue 3075 and 3076 tables with source rows and
SHA-256 dataset identities. The second command:

1. Requires the requested issue and the immediately preceding issue.
2. Uses `fxm_pub_hist.pub_part`, `amend_type`, and `mod_type` to classify the
   current issue's new, modified, and withdrawn publications.
3. Retains foreign FB base-station transmitters for field-strength screening.
   ML receiving land-mobile stations remain in trend counts but are not treated
   as interfering transmitters.
4. Joins source notice, transmitter, antenna, effective-height and geography
   rows by `terrakey`, `ant_key`, and `geo_key`.
5. Finds the true nearest point anywhere along the bundled GISCO Finland
   boundary/coastline (projection onto every boundary segment, not the nearest
   vertex; see "Border geometry" below) and every co-frequency Finnish station
   supplied in the workbook, then applies
   ITU-R P.1546-6 at 10% time, 50% locations and 10 m receiver height.
6. Compares the calculated value with ECC T/R 25-08 A.1.2.3 and writes flat CSV,
   self-contained JSONL, a full screening audit, trends and a run summary.

## Criteria and model evidence

ECC Recommendation T/R 25-08, A.1.2.3 defines co-channel border thresholds in
a 25 kHz reference bandwidth: 0 dBµV/m from 29.7-47 MHz, 6 dBµV/m from
47-108 MHz, 12 dBµV/m from 108-380 MHz, 18 dBµV/m from 380-400 MHz and
20 dBµV/m from 400-470 MHz. Conditions are 50% locations, 10% time and a
10 m receiving antenna. The challenge Q&A instructs applying the above-400 MHz
value above 470 MHz for this exercise. Source:
<https://docdb.cept.org/download/4789>

Field strengths use the published P.1546-6 Python implementation pinned to
commit `e235629009ab1a12a33fc4a8fb5612f2883ecb5b`. P.1546-6 covers 30-4000 MHz,
paths up to 1000 km and provides field strength/basic transmission loss. Sources:
<https://www.itu.int/rec/R-REC-P.1546-6-201908-I/en> and
<https://github.com/eeveetza/Py1546>.

Station-class meanings, FXM field units and power types come from the terrestrial
BR IFIC Preface. FB is a transmitting base station in the land-mobile service;
ML is a receiving land-mobile station. `pwr_dbw` is radiated power in dBW and
`pwr_eiv` identifies ERP (`E`) or EIRP (`I`). Source:
<https://www.itu.int/en/ITU-R/terrestrial/brific/BRIFIC/Preface/PREFACE_EN.pdf>

The screening geometry is Eurostat/GISCO Countries 2024, Finland at 1:10 million
in EPSG:4326. Source:
<https://gisco-services.ec.europa.eu/distribution/v2/countries/distribution/FI-region-10m-4326-2024.geojson>.

## Border geometry

T/R 25-08 assesses field strength at the border line, so the path distance is to the
nearest point *on* the boundary, which usually lies between two vertices. The GISCO
geometry has 77 rings and 726 segments. Each segment is the straight
longitude/latitude line between two GeoJSON positions (RFC 7946, 3.1.1). For each
transmitter, every segment is ranked with a local equirectangular projection (in which
these segments stay straight). Every segment within 25% + 2 km of the best
projected distance is then refined by minimising the haversine distance along the
segment (sampling plus golden-section search). Unit tests check the result against an
exhaustive refinement of all segments and against dense sampling.

Method v1.0 used the nearest *vertex*. For IFIC 3076 this changed one finding:
a Russian 793.5 MHz transmitter, 21.58 km → 13.40 km, margin +10.95 dB → +20.42 dB. It
stays `exceeds_threshold`. The other 22 findings and all counts are unchanged. A longer
vertex distance understated the field strength, so the old value was not conservative.

## Outputs and interpretation

- `terrestrial_ific3076_findings.csv` is the evaluator-friendly flat result.
- `terrestrial_ific3076_findings.jsonl` contains each source notice, source-row
  links, model inputs, assumptions, criterion citation and full-precision result.
- `terrestrial_ific3076_screening.jsonl` also records candidates excluded because
  their nearest Finland point is beyond P.1546's 1000 km path limit.
- `terrestrial_trends.json` lists the largest issue-to-issue changes by
  administration and 100 MHz band.
- `terrestrial_summary.json` records exact input hashes, method versions, counts,
  assumptions and deterministic run ID.

This is a reproducible screening result, not an official coordination study.
The geometry is a generalised national boundary/coastline, not the legal outer
limit of Finland's territorial sea. Paths are treated as all-land with rural
clutter and no terrain profile. The maximum available ERP and effective height
are used. No bandwidth correction is applied because occupied bandwidth does
not establish channel spacing or uniform spectral power. These assumptions are
repeated in every run summary, and an exceedance is an expert-review trigger,
not proof of harmful interference.
