# Worst-case PFD calculation

`python -m app calculate-pfd` reads `output/calculation-readiness/` and the review
cases, and writes `output/pfd-calculations/`:

- `case_pfd_results.jsonl`: one record per case with geometry, the emission and beam
  that were used (source rows), every candidate Table 21-4 criterion with its
  conditions, caveats, pfd, limit and margin, and the case verdict.
- `case_pfd_results.csv`: one flat row per case for expert review.
- `pfd_summary.json`: method, assumptions, status definitions and counts.

## Formula

```
pfd(δ) = P_ref + G_max − 10·log10(4π·d(δ)²)      dB(W/m²) in the reference bandwidth B_ref
margin = limit(δ) − pfd(δ)                       negative = calculated exceedance
```

| Term | Source | Note |
| --- | --- | --- |
| `P_ref` | `emiss.pwr_ds_max` (dBW/Hz) + 10·log10(B_ref), capped at `emiss.pep_max` (dBW) | RR Appendix 4: density averaged over the worst 4 kHz below 15 GHz, worst 1 MHz at or above 15 GHz |
| `G_max` | `s_beam.gain` (dBi), highest beam of the case's groups | Peak gain toward the station (Traficom: worst case always) |
| `d(δ)` | GSO: `geo.long_nom`; non-GSO: `orbit.perig_km/apog_km/op_ht_km`, `inclin_ang` | Spherical Earth, free space (RR No. 21.16) |
| `limit(δ)` | `app/reference/pfd_criteria.json` (RR Table 21-4) | See `docs/PFD_CRITERIA.md` |

## Geometry

- **GSO:** one elevation angle and distance per station. A satellite below the
  horizon from the station is `not_visible` and cannot interfere there.
- **Non-GSO:** the satellite moves, so the angle of arrival is swept from 0° to the
  highest elevation the orbit can reach over the station's latitude (in 0.1° steps,
  plus every segment boundary of the limit). The smallest margin over the sweep is
  reported. The pfd is highest overhead, but the limit is strictest near the
  horizon, so the worst point depends on altitude and on the limit's shape. Distance
  uses the lowest filed altitude (perigee) and visibility the highest (apogee), which
  is a deliberate upper bound for elliptical orbits.
- **Constellation parameters:** `Y` (No. 21.16.15) from `non_geo.nbr_sat_nh/nbr_sat_sh`;
  `X` (No. 21.16.6) from the total `orbit.nbr_sat_pl` up to 999 satellites. Larger
  constellations need `Nv`, which the IFIC database does not contain, so those rows are
  reported as `parameter_missing`.
- **Orbit-derived conditions:** HEO (inclination 35°-145°, apogee > 18 000 km) and
  "99 or fewer satellites" are resolved. Rows whose condition fails are shown but do not
  decide the verdict. Service-specific applicability is not yet resolved
  (`orbit_and_frequency_match_service_unverified`).

## Service applicability

RR No. 21.16 applies each limit to "emissions by a space station of the service
indicated". Each frequency group's ITU station class (`srv_cls.stn_cls`) is mapped to
services through `backend/src/app/reference/station_classes.json`, citing the IFIC
Preface (October 2026), Section IV, Table 3. For each Table 21-4 row:

| Group's service | Effect |
| --- | --- |
| match (e.g. `EC` for a fixed-satellite row) | The group's emissions decide the row. |
| ambiguous (`ED`/`EK`/`ER` telemetry, tracking or telecommand outside space-operation rows, per RR No. 1.23; `EW` for EESS-active rows) | Used only when no group matches; the verdict stays a candidate. |
| unknown (no class, or an earth-station class) | Same as ambiguous. |
| known mismatch (e.g. `EN` radionavigation) | Ignored. If every group mismatches, the row is `not_applicable`. |

A row is `applicable` when the service matches and every footnote condition is
satisfied. Footnote 21.16.6A (17.7-19.3 GHz) now uses the service and the notice receipt
date: MetSat or GSO satisfies it; non-GSO FSS received after 17 November 1995 fails it,
so those satellites are judged by the 21.16.6 (X) row instead. A confirmed row decides the
verdict; stricter unconfirmed rows are listed in `stricter_unconfirmed_rows`.

## Equal-rights sharing (RR No. 21.16), Article 5 and M4

No. 21.16 applies a Table 21-4 limit "where the frequency bands are shared with equal rights
with the fixed or mobile service, unless otherwise stated". This is checked per Region 1
sub-band, not assumed.

**Legal test: Article 5, Region 1.** `backend/src/app/reference/article5_region1.json`
transcribes the Region 1 allocations (66 sub-bands, page-cited) for every Table 21-4 band
that applies in Finland, including Region-wide footnote allocations (5.447B, 5.487A,
5.538, 5.540). Every footnote in those cells was checked for Finland; only 5.536B/5.536C
name Finland, and they do not change allocations. For each sub-band:

| Result | Meaning | Effect |
| --- | --- | --- |
| `equal_rights` | The satellite's service has a transmitting allocation (space-to-Earth, space-to-space or no direction) of the same category as fixed or mobile. | Spectrum kept. |
| `explicitly_applicable` | The regulations say the limit applies anyway (No. 5.544, 31-31.3 GHz space research). | Spectrum kept. |
| `unequal_rights` | Categories differ, e.g. EESS (active) primary vs fixed secondary in 9.9-10 GHz (5.477 does not list Finland). | Spectrum excluded. |
| `partner_not_allocated` | No fixed or mobile allocation, and no stated alternative basis. | Spectrum excluded. |
| `service_not_allocated` | The satellite's service has no transmitting allocation in Region 1 (RR No. 4.4). | Spectrum excluded; case flagged. |

Rows that state another sharing basis carry `sharing_basis` in the limits table:
1 670-1 700 MHz (meteorological aids, cell text), 1 670-1 690 MHz (No. 21.16.5),
13.4-13.65 GHz (No. 21.16.9: EESS (active) and space research), and 31-31.3 GHz (No. 5.544).
The worst emission is chosen only from the spectrum that passes. If nothing passes, the
row is `not_applicable` with `not_applicable_reason: rr_21_16_equal_rights_sharing_not_met`.

**National context: M4.** The Traficom open-data snapshot
(`docs/reference/traficom-m4/`, M4 4 AG/2026M) gives, per evaluation, whether Finland lists
the partner service (`partner_in_finland`: primary, secondary or not_listed) and the
satellite service. M4 lists services "in use or intended to be used" in Finland, so it is
narrower than Region 1 (e.g. 2 200-2 245 MHz lists only FIXED). It does not change the
legal result. It tells the expert whether there is national fixed or mobile use to
protect. Each verdict carries it as `national_context_m4`.

## Verdicts

Margins are classified at full precision and rounded only in the exported files.

| Status | Meaning |
| --- | --- |
| `exceeds_limit` / `near_limit` / `below_limit` | Margin < 0, 0 to < 3 dB (`--near-margin-db`), ≥ 3 dB against a row whose applicability is confirmed. None yet. |
| `candidate_exceeds_limit` / `candidate_near_limit` / `candidate_below_limit` | Same margin classes, but the governing row's service applicability is unverified or a footnote condition is unresolved. Every current verdict is a candidate. |
| `special_method_required` | Only rows with a prescribed special method apply (No. 21.16.8 SAR mean pfd; No. 21.16.19 Resolution 679 Annex 2). The generic value is kept as `screening_estimate` for context. |
| `parameter_missing` | The applicable row needs X (`Nv` for N ≥ 1000), which the IFIC database lacks. |
| `no_criterion` | No Table 21-4 row; the maximum pfd in 4 kHz and 1 MHz is reported for context. |
| `unallocated_service_rr_4_4` | The satellite's service has no Region 1 allocation in the band. No Table 21-4 limit applies, but under RR No. 4.4 it must not cause harmful interference. Reference pfd reported. |
| `not_visible` / `missing_input` / `not_space_station` | Below the horizon / missing technical input / not a space station. |

Each criterion is evaluated once, against the worst emission over all of the case's
frequency segments that fall in its bands, so the result does not depend on segment
order.

Special methods are declared in the limits table (`special_method`), not in code. For
No. 21.16.8 the generic value is a proven upper bound of the mean SAR pfd (duty cycle ≤ 1,
vertical-plane gain ≤ peak gain), so a non-negative generic margin still counts; a
negative one is withheld. For No. 21.16.19 no upper-bound proof exists, so the generic
value never gives a verdict.

## Caveats that make results pessimistic (upper bounds)

- Peak beam gain is assumed toward every station at every angle.
- Below 15 GHz, the 4 kHz peak density is scaled to 1 MHz limits as if the spectrum were
  flat (flag `density_scaled_from_worst_4khz`).
- 9.9-10.4 GHz EESS (active) limits are mean pfd including SAR duty cycle (No. 21.16.8);
  filed values are peak (flag `mean_pfd_limit`).
- Adjacent cases use in-band pfd without out-of-band attenuation.
- Advance-publication (API) filings often carry maximum envelope values.

A negative margin is therefore a reason for expert review, not proof of a violation.

## Unknown constellation parameters

X (No. 21.16.6) needs `Nv`, the maximum number of visible satellites, which the IFIC
database lacks, for constellations of 1 000 or more satellites. The definition still
gives a lower bound: X ≥ 20.3 dB for 1 000-6 000 satellites, X ≥ 1 dB above. Every
Table 21-4 formula is non-increasing in X and Y (checked by a unit test), so the bound
gives the loosest possible limit. A negative margin at the bound is an exceedance for any
valid `Nv` (`parameters_at_lower_bound` is recorded). A non-negative one stays
`parameter_missing`.

## Result for IFIC 3074 (method 1.3.0)

| Status | Cases |
| --- | ---: |
| exceeds_limit | 2,302 (38 notices; 264 decided at the X lower bound) |
| near_limit | 2,181 (27 notices) |
| below_limit | 4,284 |
| candidate_below_limit | 19 (telemetry/tracking groups only, ambiguous under RR No. 1.23) |
| special_method_required | 4 (10-10.4 GHz SAR) |
| unallocated_service_rr_4_4 | 20 (mobile-satellite downlinks in 2.5-2.69 GHz: CSN-SSO, AST-NG-C-4, STARERA-3) |
| no_criterion | 985 |
| not_visible | 4,176 |
| missing_input | 1,763 |

Against method 1.2.0, the sharing check changed 36 cases and no remaining margin:
16 SAR cases at 9.9-10 GHz moved to `no_criterion` (fixed is secondary there in Finland),
and 20 mobile-satellite cases (14 previously exceeding, 6 below the limit) moved to
`unallocated_service_rr_4_4`. For all
8,786 verdicts, M4 lists fixed or mobile as primary in Finland. GSO exceedances are
within 0.1-7 dB (Ka-band and C-band networks). The largest non-GSO margins come from
high-gain LEO beams, large Ka-band constellations and launch vehicles at 160 km altitude.
