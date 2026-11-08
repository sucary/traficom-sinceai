# Risk assessment documentation

## Purpose

The solution reviews ITU BR IFIC data for cases that may affect radio-frequency use in Finland. It does not modify the original IFIC databases. It reads them, combines them with Finnish frequency information, performs deterministic calculations, and produces results for expert review.

The solution has two analysis paths:

1. Space IFIC 3074: satellite power flux density assessment.
2. Terrestrial BR IFIC 3076: land-mobile field-strength assessment.

The results shown in the application come from these calculations. The application presents the important findings in a simpler form, while the output files retain the detailed evidence.

## Inputs

### Space analysis

| Input | Purpose |
| --- | --- |
| `data/ific3074.mdb` | The Space IFIC issue being evaluated. It contains the notices and their frequency, emission, beam, and orbit data. |
| `data/Traficom_SinceAI_Frequencies_of_interest_v05112026.xlsx` | Finnish stations and frequencies that the solution protects and uses for matching. |
| `data/SPS_ALL_IFIC3083.mdb` | Optional reference snapshot for Appendix 30 and 30A records. Used for context when present; not part of the IFIC 3074 result count. |
| `data/30B_3083.mdb` | Optional reference snapshot for Appendix 30B records. Used for context when present; not part of the IFIC 3074 result count. |
| Radio Regulations criteria stored by the application | The applicable power flux density limits and their conditions. |
| ITU Radio Regulations Article 5 allocation data stored by the application | Used to confirm whether the satellite service and the terrestrial sharing service have equal allocation rights in Region 1. |
| Finnish M4 frequency-allocation data stored by the application | Reports whether the relevant terrestrial service is used or planned in Finland. |

### Terrestrial analysis

| Input | Purpose |
| --- | --- |
| `data/brific3075.mdb` | Optional previous terrestrial issue. When present, it adds the issue-to-issue comparison; new, modified and withdrawn assignments and all findings come from issue 3076 itself. |
| `data/brific3076.mdb` | The terrestrial issue being evaluated. |
| `data/Traficom_SinceAI_Frequencies_of_interest_v05112026.xlsx` | Finnish station locations and protected frequencies used for additional station-level checks. |
| `backend/src/app/reference/finland_assessment_boundary.geojson` | Finland's land border and territorial-sea outer limit used as calculation points. |
| ECC Recommendation T/R 25-08 criterion | The field-strength threshold used for the land-mobile screening. |
| ITU-R P.1546-6 implementation | The propagation model used to calculate terrestrial field strength. |
| Finnish M4 frequency-allocation data stored by the application | Provides national frequency-use context for each finding. |

Each imported input receives a SHA-256 hash. The hash identifies the exact version of the file used in a calculation run.

## Space IFIC 3074 Analysis

### 1. Read the source data

The pipeline extracts the relevant relational tables from `ific3074.mdb`. It keeps the original source row numbers and the input-file hash. This makes it possible to trace a result back to the original database record.

The original database contains 196 notices. A notice can contain many frequency groups, emissions, beams, and orbit records, so one notice can produce several assessment cases.

### 2. Find frequencies relevant to Finland

The solution compares space-to-Earth transmissions with the Finnish frequencies in the supplied workbook.

A match is retained when:

- the satellite and Finnish frequency ranges overlap; or
- the ranges are adjacent, with a gap no larger than one protected Finnish bandwidth.

Both Finnish receive and transmit frequencies are checked. A frequency match is only a screening result. It does not by itself mean that interference will occur.

For IFIC 3074, 139 of the 196 notices had at least one overlapping or adjacent Finnish frequency.

### 3. Build assessment cases

Repeated low-level matches are grouped into review cases. One case represents one satellite notice assessed against one Finnish station and one protected frequency role.

The IFIC 3074 data produced 15,982 review cases. After publication-stage and object-type classification, 15,734 cases continued to the calculation stage.

### 4. Prepare the technical values

For every case, the solution collects:

- the satellite orbit information;
- the filed emission power or power density;
- the satellite beam gain;
- the frequency range and service class; and
- the Finnish station location and protected band.

When the free IFIC data does not contain a beam direction, the calculation assumes that the filed peak beam gain points toward the Finnish station. This is a conservative worst-case assumption.

### 5. Calculate satellite power flux density

The calculation first determines the radiated power in the reference bandwidth and adds the filed antenna gain to obtain EIRP. It then applies free-space spreading over the satellite-to-station distance:

`PFD = EIRP - 10 log10(4 pi distance squared)`

For geostationary satellites, the distance and elevation are calculated from the orbital longitude and the Finnish station location. For non-geostationary systems, the calculation searches the reachable elevation range and keeps the worst result.

For adjacent-frequency cases, the calculation does not apply an out-of-band attenuation value because that value is not established by the source data. The result is therefore an upper-bound screening value.

### 6. Apply the regulatory limit

The calculated PFD is compared with an applicable limit from Radio Regulations Article 21, Table 21-4. The solution checks the frequency, orbit type, satellite service, station class, reference bandwidth, and relevant conditions before applying a limit.

The space margin is calculated as:

`margin = regulatory limit - calculated PFD`

- A negative margin means that the calculated PFD is above the limit.
- A margin from 0 dB to less than 3 dB is near the limit.
- A margin of 3 dB or more is below the limit.

Some cases cannot receive a final numerical decision because an input or a required regulatory parameter is missing. These cases remain visible for expert review instead of being silently discarded.

### Space results

The completed IFIC 3074 run produced 15,734 case results:

| Result | Cases | Meaning |
| --- | ---: | --- |
| Exceeds limit | 2,302 | The worst-case PFD is above a confirmed applicable limit. |
| Near limit | 2,181 | The result is less than 3 dB below the limit. |
| Below limit | 4,284 | The result is at least 3 dB below the limit. |
| Not visible | 4,176 | The satellite cannot be above the horizon for that Finnish station under the filed orbit. |
| Missing input | 1,763 | A required technical value is unavailable. |
| No applicable criterion | 985 | No applicable Table 21-4 criterion was found. |
| Unallocated service under RR No. 4.4 | 20 | The service is not allocated in Region 1 for the assessed band. |
| Candidate below limit | 19 | A value was calculated, but applicability could not be fully confirmed. |
| Special method required | 4 | The regulation requires a method that cannot be completed with the available input. |

These are case counts, not notice counts. The application groups related cases under their notice and shows 60 IFIC 3074 notices of concern. A notice is shown when at least one case exceeds a limit, is near a limit, or concerns an unallocated service.

## Terrestrial BR IFIC 3076 Analysis

### 1. Compare consecutive issues

The solution compares issues 3075 and 3076 to identify new, modified, and withdrawn terrestrial assignments. It then selects foreign transmitting land-mobile base stations. Finnish assignments and unrelated station types are not sent to the propagation calculation.

### 2. Check relevance to Finland

Each selected transmitter is assessed against:

- the nearest relevant point on every section of Finland's land border;
- the outer limit of Finland's territorial sea; and
- co-frequency Finnish stations in the supplied workbook.

The calculation retains the assessment point that produces the highest field strength. A transmitter farther than 1,000 km from every assessment point is recorded as outside the P.1546 model distance and is not given a calculated finding.

### 3. Calculate field strength

The solution uses ITU-R P.1546-6 with the filed frequency, maximum available ERP, effective antenna height, distance, and path type.

Land-border paths use the Land curve. Territorial-sea paths use the Cold-sea curve. When the path to a Finnish protected station cannot be classified reliably, both curves are calculated and the larger field strength is retained.

The screening uses a 10 m receiving height, 10% time, and 50% locations. It does not use a terrain profile, so the result is a conservative screening calculation rather than a site-specific interference prediction.

### 4. Apply the coordination threshold

The calculated field strength is compared with the applicable threshold from ECC Recommendation T/R 25-08, section A.1.2.3.

The terrestrial margin is calculated as:

`margin = calculated field strength - threshold`

- A positive margin means that the calculated field strength exceeds the threshold.
- A margin from -3 dB through 0 dB is near the threshold.
- A margin below -3 dB is below the threshold.

The sign is opposite to the space margin because the terrestrial calculation subtracts the threshold from the calculated field strength.

### Terrestrial results

The completed BR IFIC 3076 run produced:

| Result | Assignments | Meaning |
| --- | ---: | --- |
| Screened events | 720 | New, modified, or withdrawn foreign land-mobile events considered by the analysis. |
| Outside model distance | 697 | More than 1,000 km from every usable assessment point. |
| Calculated findings | 23 | Within the model range and calculated with P.1546. |
| Exceeds threshold | 9 | The worst calculated field strength is above the coordination threshold. |
| Near threshold | 0 | No result was within 3 dB below the threshold. |
| Below threshold | 14 | The calculated result is more than 3 dB below the threshold. |

The application displays the nine assignments that exceed the threshold. No supplied Finnish workbook station was above the threshold in this run; the governing exceedances occurred at boundary assessment points.

## Output Files

### Space IFIC 3074 outputs

| Output | Purpose |
| --- | --- |
| `output/ific3074/pfd-calculations/case_pfd_results.jsonl` | Complete authoritative case records. Each record contains the calculation, regulatory evaluation, assumptions, caveats, source rows, and input hashes. |
| `output/ific3074/pfd-calculations/case_pfd_results.csv` | Flat machine-readable version of the main result fields. Some provenance cells are longer than Excel's cell limit, so the JSONL file remains the authoritative full output. |
| `output/ific3074/pfd-calculations/pfd_summary.json` | Method version, run identifier, parameters, status definitions, assumptions, and result counts. |
| `output/ific3074/analysis_pipeline_summary.json` | Stage counts and checks proving that records were carried consistently from one processing stage to the next. |

### Terrestrial BR IFIC 3076 outputs

| Output | Purpose |
| --- | --- |
| `output/brific3076/terrestrial_ific3076_findings.jsonl` | Complete calculated findings, including all assessment points, source notice data, model parameters, criterion, and sources. |
| `output/brific3076/terrestrial_ific3076_findings.csv` | Flat evaluator-friendly table of the 23 calculated findings. |
| `output/brific3076/terrestrial_ific3076_screening.jsonl` | All 720 screened events, including the 697 events outside the model distance. |
| `output/brific3076/terrestrial_summary.json` | Run identifier, model version, assumptions, input hashes, regulatory framework, and result counts. |
| `output/brific3076/terrestrial_trends.json` | Issue-to-issue activity changes and detected anomalies. |

### Application output

`frontend/public/data/assessment.json` is generated from the detailed result files. The application uses it to group cases by notice, rank concerns, and present the calculations in a readable form.

The application intentionally shows a smaller set than the output files:

- Space: notices with an exceedance, a near-limit result, or an unallocated service.
- Terrestrial: assignments that exceed or are near the field-strength threshold.

The application is the review interface. The JSONL, CSV, and summary files are the separate processed outputs used for traceability and accuracy evaluation.

## Reproducibility and Traceability

The two required analyses can be run from the project root:

```powershell
.venv\Scripts\python.exe -m app run ific3074.mdb
.venv\Scripts\python.exe -m app run brific3076.mdb
```

The pipeline records:

- the SHA-256 hash of every input;
- the processing method and version;
- the calculation parameters;
- the source table and row numbers;
- the regulatory provision used;
- the assumptions and missing inputs; and
- a run identifier derived from the method, parameters, and inputs.

The Space pipeline also validates the number of records passed between its matching, grouping, classification, readiness, and calculation stages. The completed IFIC 3074 run passed all of these count checks.

## Interpretation of the Results

The output is designed to support expert review. An exceedance is a reason to investigate and, where appropriate, prepare correspondence. It is not by itself proof that harmful interference will occur.

The main conservative assumptions are:

- satellite peak beam gain is directed toward each Finnish station;
- adjacent-frequency space cases do not receive an assumed out-of-band attenuation;
- the worst usable emission and beam gain are selected;
- terrestrial calculations use maximum available ERP and effective antenna height;
- terrestrial paths do not include detailed terrain profiles; and
- uncertain terrestrial land or sea paths use the larger calculated field strength.

These choices reduce the chance of overlooking a possible concern. They can also produce false positives, which is why the application exposes the calculation, assumptions, source records, and regulatory basis for expert review.

## Basis of This Description

This description is based on the executable pipeline and the generated manifests and summaries from the completed IFIC 3074 and BR IFIC 3076 runs. It does not rely on draft narrative documents elsewhere in the repository.
