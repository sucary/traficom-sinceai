# Application structure

The root contains sibling `frontend/` and `backend/` directories. The current backend
is a Python package; the frontend is a placeholder. No web server, frontend framework,
AI provider, queue or deployment environment has been scaffolded yet.

## Current responsibilities

| Location | Responsibility |
| --- | --- |
| `backend/src/app/cli.py` | Parse commands and route work |
| `backend/src/app/config.py` | Resolve checkout defaults and shared connection arguments |
| `ingestion/prepare.py` | Coordinate file preparation |
| `ingestion/access.py` | Extract selected Access tables |
| `ingestion/workbook.py` | Read workbook rows and verify source formulas |
| `ingestion/stations.py` | Convert units and flag questionable station values |
| `ingestion/specs.py` | Describe the supported challenge input layouts |
| `ingestion/manifest.py` | Hash files and serialize provenance |
| `db/connection.py` | Establish certificate-verified connections |
| `db/loader.py` | Import prepared records transactionally |
| `db/migrations.py` | Apply and track packaged SQL migrations |
| `backend/tests/unit/` | Tests without database access |
| `backend/tests/integration/` | Explicit checks against a disposable local database |

The backend package is named `app`. All commands use `python -m app`; the old
`pipeline.*` compatibility package has been removed.

## Planned ownership

Add these modules when the relevant feature is implemented:

- `frontend/`: findings, maps, dashboards and the assistant UI.
- `app/api/`: HTTP endpoints and request/response models.
- `app/analysis/`: deterministic matching, calculations and evidence assembly.
- `app/assistant/`: AI explanations and correspondence drafts.
- `app/jobs/`: execution of import and analysis work outside HTTP requests.
- Root `deploy/`: container and hosting configuration.

The frontend calls the backend API. The API and worker share the same Python package
and PostgreSQL access code. Calculations belong in analysis modules so command-line
jobs and HTTP endpoints use the same implementation. Database credentials and AI
provider credentials belong in backend runtime configuration.

## Data and schema boundaries

Original inputs remain in `data/` and reference documents in `docs/`. Generated
exports remain in ignored `output/`. Keeping these paths stable preserves existing
manifest file names and team workflows. Certificates remain in ignored `certs/`.

PostgreSQL keeps three existing schema responsibilities: `ingestion` preserves
source records, `core` provides typed views, and `analysis` stores runs and findings.
This refactor changes code organization, not those schemas or their existing records.

Migrations are packaged alongside the database code. They run explicitly and record
their name and checksum in `ingestion.schema_migrations`. Imports do not run migrations.
Previously applied SQL must remain immutable; schema changes require a new file.
