# Repository architecture

| Folder | Purpose |
| --- | --- |
| `backend/src/app/` | Python application code. |
| `backend/src/app/ingestion/` | Extract datasets, normalize values, and record provenance. |
| `backend/src/app/db/` | PostgreSQL connections, data loading, and SQL migrations. |
| `backend/tests/` | Unit tests and local database integration checks. |
| `frontend/` | Placeholder for the future web interface. |
| `docs/` | Reference documents, database instructions, and data notes. |
| `data/` | Original challenge datasets. |
| `output/` | Generated exports, logs, and test artifacts; ignored by Git. |
| `certs/` | Local database certificates; ignored by Git. |

Run backend commands with `python -m app prepare`, `match-frequencies`,
`consolidate-frequency-matches`, `classify-frequency-cases`, `criteria-coverage`, `calculate-pfd`, `load`, or `migrate`.
Regulatory reference data (PFD criteria from RR Table 21-4) lives in
`backend/src/app/reference/`; see `docs/PFD_CRITERIA.md`. The worst-case PFD
method is in `docs/PFD_CALCULATION.md`.
To evaluate another Space IFIC, run `rebuild-analysis --ific ificNNNN.mdb --output-root output/ificNNNN`
(see `docs/PROCESSING_NEW_IFIC.md`; IFIC 3075 is the worked example).
Use `check-calculation-readiness` to assemble validated technical inputs without
performing PFD or regulatory-limit calculations.
Dependencies are defined in `backend/pyproject.toml`.

Current data flow: **source files → preparation → deterministic frequency matching → review-case consolidation → regulatory classification → calculation readiness → later calculations / AI analysis**.
