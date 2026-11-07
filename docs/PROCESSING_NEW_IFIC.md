# Processing another Space IFIC

Any Space IFIC published as an SNS version 10 database (`ificNNNN.mdb`, ITU format since
7 January 2025) runs through the same pipeline as 3074. The AP30/30A and AP30B snapshots
(`SPS_ALL_IFIC3083.mdb`, `30B_3083.mdb`) and the Traficom workbook are shared context.

## Steps

1. Download the issue from the ITU Space IFIC page
   (https://www.itu.int/sns/wic/demowic26.html lists 2026 issues, e.g.
   https://www.itu.int/sns/ific10/ific3075.zip), unzip it in an empty folder, and copy
   `ificNNNN.mdb` into `data/`.
2. Run the whole pipeline into its own folder:

   ```powershell
   .\.venv\Scripts\python.exe -m app rebuild-analysis --ific ific3075.mdb --output-root output/ific3075
   ```

   This extracts the raw inputs, then runs matching, consolidation, classification,
   readiness, criteria coverage and the PFD calculation in a staging folder. It checks that
   counts agree from stage to stage, and publishes everything only if they do
   (`analysis_pipeline_summary.json`). The file name must match `ificNNNN.mdb`. Missing
   inputs stop the run before any work.

## Demonstration: IFIC 3075 (published 7 July 2026)

| Item | Value |
| --- | --- |
| Source | https://www.itu.int/sns/ific10/ific3075.zip, downloaded 2026-11-07 |
| SHA-256 (zip) | `ab6a4c23fec02f7ca3c21e6eebbd282d2d22dbee4360ede81174c77d7524e188` |
| SHA-256 (`ific3075.mdb`) | `5416d9e8a67fc22fb055cb0b6f457e8bb205df90d3e6e0a0dccd9be0ede02a07` |
| Code changes needed | None in extraction, matching or calculation. The pipeline gained an `--ific` option, and a classification reason that named "IFIC 3074" now uses the case's issue. |
| Pipeline status | `completed_and_validated`. All four cross-stage count checks match. |

| Stage | IFIC 3074 | IFIC 3075 |
| --- | ---: | ---: |
| Match candidates (all space datasets) | 203,572 | 57,036 |
| Review cases | 20,512 | 13,120 |
| Calculation queue / PFD results | 15,734 | 7,836 |
| exceeds_limit | 2,302 (38 notices) | 982 (22 notices) |
| near_limit | 2,181 | 550 |
| below_limit | 4,284 | 3,287 |
| unallocated_service_rr_4_4 | 20 | 15 |
| no_criterion / not_visible / missing_input | 985 / 4,176 / 1,763 | 1,194 / 1,777 / 31 |

The two issues share no notices. Largest 3075 margins: BISTROMATH (UAE, non-GSO, Ka-band,
−25.5 dB), PROBA-3.0 (F, 2.2 GHz, −17.1 dB), ISS access (USA, −13.7 dB), and
LUX-G18 GSO networks (−6.8 to −8.7 dB in 17.7-19.3 GHz).

What the new issue surfaced: 12 cases (four Article 11.2 notices) have no publication
part (`wic_part`) in 3075. The classifier does not guess. It marks them
`needs_information`, and they are kept out of the calculation queue.
