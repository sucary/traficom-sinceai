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

Run backend commands with `python -m app prepare`, `load`, or `migrate`.
Dependencies are defined in `backend/pyproject.toml`.

Current data flow: **source files → preparation → PostgreSQL on Aiven**.
