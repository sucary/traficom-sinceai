# Satellite-to-Finnish frequency matching

The matching stage creates screening candidates for later technical analysis. It does
not calculate PFD, field strength, propagation, protection limits, margins, or risk.
An overlap is not proof of harmful interference.

## Rules implemented

- Preserve the source MDB and workbook files unchanged.
- Treat ITU `freq.emi_rcp = E` records as satellite emissions (downlinks).
- Protect both RX and TX frequencies in the Finnish workbook. If they are identical,
  represent them once as `rx_tx`; if RX is absent, TX remains protected.
- Use the smaller of channel bandwidth and transmission bandwidth when both are
  available. Compact values such as `5000k`, `8M00`, `10k0`, `7,6k`, and `0,1G`
  are normalized to Hz.
- Match closed frequency intervals. Round half-Hz endpoints outward so screening
  cannot lose a boundary overlap.
- Screen two relations (brief: "same or adjacent frequency range"; Traficom Q&A:
  concerns can arise from high PFD *near* the frequency):
  - `co_frequency`: the closed intervals intersect. Records `overlap_hz`,
    `overlap_fraction_of_protected`, and whether the satellite band `covers` the
    protected band or is `partial`.
  - `adjacent`: no intersection, but the gap is at most N × the protected
    bandwidth (`--adjacent-channels N`, default 1; `0` disables). Records
    `separation_hz` and whether the satellite band lies `below` or `above`.
- Do not filter on satellite beam pointing; retain the stated worst-case assumption.
- Do not yet filter on notice status, action code, or publication history, and do not
  deduplicate repeated source frequency rows. Those regulatory interpretations belong
  in a later, separately testable stage.
- Keep IFIC 3074, AP30/30A 3083, and AP30B 3083 provenance and dataset roles distinct.

## Run locally

First prepare the three MDB files and the Finnish workbook:

```powershell
.\.venv\Scripts\python.exe -m app prepare `
  --only ific3074.mdb `
  --only SPS_ALL_IFIC3083.mdb `
  --only 30B_3083.mdb `
  --only Traficom_SinceAI_Frequencies_of_interest_v05112026.xlsx
```

Then create the matching artifacts:

```powershell
.\.venv\Scripts\python.exe -m app match-frequencies
```

Consolidate repeated source-row matches into review cases:

```powershell
.\.venv\Scripts\python.exe -m app consolidate-frequency-matches
```

Classify every review case using public ITU codes:

```powershell
.\.venv\Scripts\python.exe -m app classify-frequency-cases
```

Assemble and validate the inputs needed by the future PFD implementation:

```powershell
.\.venv\Scripts\python.exe -m app check-calculation-readiness
```

The ignored `output/frequency-matches/` directory contains:

- `frequency_match_candidates.jsonl`: full provenance-oriented records for later
  deterministic calculations and AI input.
- `frequency_match_candidates.csv`: flat expert-review export.
- `frequency_match_summary.json`: method, assumptions, dataset roles, and counts. Counts are split by relation.

The ignored `output/frequency-cases/` directory contains a JSONL and CSV with one
case per space dataset, satellite notice, Finnish workbook row, and protected RX/TX
band. Each case retains the contributing `freq` source rows, group IDs, beam names,
satellite references, unique satellite bands, and merged overlap segments. This
reduces repetition without interpreting regulatory status or calculating risk.

The ignored `output/classified-cases/` directory contains all cases with explicit
dataset role, GSO/non-GSO notice object, publication family, publication stage,
action and disposition. The mappings follow the [May 2026 ITU BR IFIC Space
Services Preface](https://www.itu.int/en/ITU-R/space/Preface/preface_e.pdf).
`st_cur` is preserved but not interpreted because the Preface marks it as BR
internal-use processing status. A separate JSONL queue contains only IFIC 3074
cases eligible for later calculations; no classified case is deleted.

The ignored `output/calculation-readiness/` directory separates notice-level orbit
profiles, frequency-level power/beam profiles and case-level station readiness. The
stage validates source presence and records worst-case assumptions. It does not
calculate geometry, PFD, regulatory limits, margins or concern status. Power and gain
units follow the ITU Preface: `emiss.pep_max` in dBW, `emiss.pwr_ds_max` in dBW/Hz,
and `s_beam.gain` in dB.

Each case carries a `frequency_relation` block (`co_frequency` if any source row
intersects the band, otherwise `adjacent`, with the nearest gap). The same
directory also holds `notice_rollups.jsonl` and `notice_rollups.csv`: one row per
space dataset and notice, with the affected Finnish stations, co-frequency and
adjacent case counts, and merged satellite frequency ranges. This is the
natural unit for AI summarisation and for draft correspondence to the
notifying administration.

## Results (method 1.1.0, adjacent channels = 1)

| Dataset | Co-frequency cases | Adjacent-only cases | Notices | Station bands |
| --- | ---: | ---: | ---: | ---: |
| IFIC 3074 | 13,783 | 2,199 | 139 | 1,115 |
| AP30/30A 3083 | 1,714 | 374 | 131 | 20 |
| AP30B 3083 | 2,164 | 278 | 120 | 36 |
