# PFD criteria reference

`backend/src/app/reference/pfd_criteria.json` holds the power-flux-density limits that
later calculations compare against. `app.reference.pfd_criteria` loads them, selects
the ones that apply to a satellite frequency range and orbit, and evaluates them at an
angle of arrival. It calculates no pfd itself.

## Source

ITU Radio Regulations, Edition of 2024, Volume 1, Article 21, No. 21.16 and
**Table 21-4 (Rev.WRC-23)**. The official PDF, its download URL and SHA-256 are in
`docs/reference/itu-rr-2024/SOURCE.txt`. Every criterion records its printed page and
PDF page, the footnotes (21.16.x) that govern it, and the printed cell text next to the
machine formula.

Transcription status: **`unverified_ai_transcription`**. The values were read from the
rendered PDF pages and cross-checked against a text extraction. A human reviewer should
check each row against PDF pages 297-301 and then set `transcription.verified_by`.

## Model

- One criterion = one table cell group: bands, services, orbit (`gso`, `non_gso`,
  `any`), reference bandwidth, and piecewise `segments` over the angle of arrival
  δ (0-90°). Each segment carries a `formula` in `d`, optionally `X` (No. 21.16.6) or
  `Y` (No. 21.16.15), and the printed `source_text`.
- Formulas use only numbers, `+ - * /`, brackets and `log10()`. They are parsed with an
  allow-list, never `eval`.
- Angle boundaries belong to the lower segment (the table uses `≤` on the upper bound).
- Cells listing two limits joined by "and" (6 825-7 075 MHz) are two criteria that
  both apply. Cells listing alternatives ("or", 17.7-19.3 GHz) are separate criteria
  with `conditions` naming the governing footnote.
- `applies_in_finland` is false for bands limited to Regions 2/3, to the United States,
  or to countries named in Article 5 footnotes 5.381/5.382, 5.403/5.404, 5.453/5.455,
  5.494/5.496 or 5.549. Finland is not listed in any of them.
- Where the printed cell does not align bands with services row by row, every listed
  service is kept for every band (conservative).
- A lookup with no matching row returns an explicit `no_criterion` record.

Not yet included: the RR Appendix 5 coordination thresholds, the pfd limits in Article 5
footnotes, the AP30/30A/30B annex limits, and CEPT material. These will be added as
separate criterion kinds (`coordination_threshold`, `concern_threshold`).

## Coverage report

```powershell
.\.venv\Scripts\python.exe -m app criteria-coverage
```

This writes `output/pfd-criteria/case_criteria_coverage.csv` (one row per review case)
and `criteria_coverage_summary.json`. A case is judged only at the satellite frequencies
that touch the Finnish band: the overlap for co-frequency cases, and the satellite band
clipped to the protected band ± one bandwidth for adjacent cases. Orbit comes from the
notice type (G = GSO, N = non-GSO, otherwise unknown).

Result for IFIC 3074 (method 1.1.0 cases):

| Finnish frequency | Cases with a Table 21-4 limit | Cases without | Notices without |
| --- | ---: | ---: | ---: |
| 30-300 MHz | 0 | 2 | 1 |
| 300 MHz-1 GHz | 0 | 750 | 9 |
| 1-3 GHz | 12,969 | 59 | 14 |
| 3-10 GHz | 549 | 168 | 14 |
| 10-20 GHz | 1,398 | 20 | 1 |
| 20-40 GHz | 67 | 0 | 0 |

Most 1-3 GHz cases are Finnish stations in 2 200-2 300 MHz, where Table 21-4 limits
EESS, space research and space operation downlinks.

Data-quality finding: AP30B 3083 has 121 `emi_rcp = E` frequency rows in
6.7-7.0 GHz and 12.75-13.25 GHz, which are AP30B uplink (Earth-to-space) bands. All
1,986 AP30B cases at 10-20 GHz come from them and are probably not real downlinks.
