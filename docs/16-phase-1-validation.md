# Phase 1 validation record

## VERIFIED ? native PostgreSQL follow-up, 2026-10-03

Environment: Windows, Python 3.12.2, native PostgreSQL **17.11**. This work closes the
PostgreSQL verification gaps from the original foundation. No Phase 2 work was undertaken.

- Service `postgresql-x64-17` was confirmed Running. A real SQLAlchemy/psycopg connection to
  `localhost:5432/rivaline` succeeded. SQL returned database `rivaline`, user `postgres`, and
  `PostgreSQL 17.11 on x86_64-windows, compiled by msvc-19.44.35229, 64-bit`.
- Configuration uses individual `POSTGRES_*` settings, constructing a SQLAlchemy URL with
  driver `postgresql+psycopg`. There is no independent `DATABASE_URL` setting.
- `.env` was confirmed Git-ignored before preparing it. The user entered the password locally;
  it was never printed or written to a tracked file. Final Git checks confirmed it is ignored
  and untracked. `.env.example` remains unchanged with a blank password.
- The existing `scripts.init_db` created the schema successfully. Read-only inspection verified
  all **23 public tables**, column names/nullability, primary keys, foreign-key column mappings,
  unique-column sets and check-constraint names against the SQLAlchemy metadata.
- The existing seed command inserted **36 rows** on its first run and **0** on its second run.
  A further repeat inserted **0** and preserved an identical full row-data fingerprint,
  including IDs, quantities and timestamps:
  `4b3f22d54c000aa5e4ac115b7eeeb5745ab5e81ce32260030b871149a77e4361`.
- Seed values, synthetic codes, material/preferred-supplier links, product/BOM links, BOM versions,
  output quantities and all material-line quantities were verified against the deterministic
  generator. Counts: products 4, raw materials 4, suppliers 3, customers 3, warehouses 2,
  bills of material 4, BOM lines 16. All other operational tables contained zero rows.
- PostgreSQL tests exercised real FK, uniqueness and check enforcement: missing item references,
  inventory item exclusivity, negative/over-reserved stock, duplicate lots/source keys,
  invalid BOM quantities/material categories/transaction direction, and mismatched BOM,
  production-batch, consumption and shipment items. A valid supplier traceability chain passed.
- PostgreSQL tests create unique schemas inside outer transactions. Session commits release
  savepoints only; rollback removes each schema and its test data. Verification found **zero**
  remaining `phase1_test_*` schemas. Demonstration data remained unchanged.
- FastAPI was started via `scripts.run_api` with a process-only port override of 18081.
  An actual HTTP request to `http://127.0.0.1:18081/health` returned **200** and
  `{"application":"Rivaline Manufacturing Integrated Operations Platform",
  "environment":"development","status":"ok","database":"up"}`.
  The temporary API process was stopped afterwards. Database settings came from local configuration.
- Default suite: **24 passed, 1 warning in 1.71s**.
- Full suite with opt-in PostgreSQL: **41 passed, 1 warning in 11.01s** (24 original cases plus
  17 PostgreSQL variants). Default tests remain independent of PostgreSQL.
- Final Ruff lint: **All checks passed!** Formatting: **44 files already formatted**.
- Dependency check: **No broken requirements found.** Twelve selected application, CLI and
  dependency modules imported successfully, including pandas, scikit-learn and psycopg.
- Git status/ignore/diff checks executed. This remains an uncommitted new repository, so
  `git diff --check` alone does not inspect untracked file contents.

## PROVIDED BUT NOT LOCALLY VERIFIED ? Docker Compose

`docker-compose.yml` remains unchanged, providing PostgreSQL 16 as the container option.
Docker Desktop cannot run on this machine because hardware virtualization is disabled
(user-provided environment limitation). Docker was not troubleshot or run in this follow-up.
Compose deployment, runtime healthcheck, container connectivity and volume persistence are
not verified locally. The earlier YAML parse was only a syntax/structure check.

## Issues and fixes

- No application schema, architecture, dependency or PostgreSQL compatibility fix was required.
- Added opt-in PostgreSQL fixtures and `scripts.verify_db` for repeatable verification.
- Initial expanded suite: **1 failed, 40 passed**. The health test's engine stub returned the
  transaction-bound PostgreSQL Connection instead of an Engine. Changed it to
  `session.get_bind().engine`; the production health service was unchanged. Final suite passed.
- Ruff initially found long lines in new verification code. Formatting and splitting one
  output string resolved them; final lint/format checks passed.
- Both test runs emit one upstream Starlette warning about the deprecated httpx TestClient
  transport. It was not suppressed and does not fail tests.
- Windows sandbox process startup failed during inspection. Approved commands outside the
  sandbox completed verification. Command-local Git safe-directory trust was used; global
  Git settings were not changed.
- Verification used the existing native installer role `postgres`. No roles or authentication
  settings were changed. A dedicated application role remains future hardening work.
- `create_all` is still bootstrap only, not migrations. Existing documented Phase 1 business
  limits (stock posting, state transitions, allocations and quality gates) remain unchanged.

## Exact command entry points executed

All Python commands below used the project virtual environment. Seed execution occurred
three times in total; verification ran before and after the final repeat.

```powershell
Get-Service postgresql-x64-17
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m scripts.seed_master_data
.\.venv\Scripts\python.exe -m scripts.seed_master_data
.\.venv\Scripts\python.exe -m scripts.verify_db
.\.venv\Scripts\python.exe -m pytest -q --postgres
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q --postgres
.\.venv\Scripts\python.exe -m ruff check tests/conftest.py scripts/verify_db.py --fix
.\.venv\Scripts\python.exe -m ruff format tests/conftest.py scripts/verify_db.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
```

Inline Python checks ran through `.\.venv\Scripts\python.exe -` to import the 12 modules,
compare verification fingerprints around a third seed execution, and launch/stop the API
subprocess with `-m scripts.run_api`. HTTP verification used Python urllib. The connection
probe executed `SELECT current_database(), current_user, version()`; verification also ran
`SHOW server_version`. These checks did not echo credentials.

Git commands were `status --short`, `diff --check`, `check-ignore .env`, and `ls-files -- .env`,
using a command-local `-c safe.directory=<workspace>` option. Reads inspected AGENTS, README,
configuration, schema, seed, API and tests. No Git commit or push was made.

## Files changed in this follow-up

- `README.md`: native PostgreSQL and Docker alternatives, configuration and live-check commands.
- `docs/16-phase-1-validation.md`: this evidence report replaces the superseded service gaps.
- `scripts/verify_db.py`: new read-only schema/seed verifier and repeat-run fingerprint.
- `tests/conftest.py`: optional PostgreSQL parametrization with transactional schema cleanup.
- `tests/test_foundation.py`: engine stub supports Engine- and Connection-bound sessions.
- `.env`: ignored local configuration prepared before the user supplied its password locally.

`docker-compose.yml`, `.env.example`, database models, seed logic and production API code
were not changed by this verification work.

## Earlier Phase 1 evidence retained

The initial foundation created all required modules, 23 entities, a deterministic master seed,
AGENTS contract and documentation. Python 3.12.2 virtual environment/dependencies were installed.
The original final suite passed 24 tests in 3.59s with the same upstream warning. Ruff and pip
checks passed. PostgreSQL DDL compilation and SQLite constraints passed; the original live API
smoke returned 503/unconfigured. Those earlier database gaps are now closed on native 17.11.
An initial inventory constraint-name collision was fixed before this follow-up.

## Stable interfaces and recommended Phase 2 next step

Preserve `database/models.py`, configuration names, lazy engine/session factory, seed transaction
ownership, `create_app`, `/health` schema and existing setup entry points. Introduce migrations
before changing persisted schema. With explicit Phase 2 approval, add small synthetic legacy
fixtures, documented mappings and audited ETL with reject/replay tests. Forecasting, reorder,
production planning and Power BI remain unimplemented. Stop after Phase 1 verification.
