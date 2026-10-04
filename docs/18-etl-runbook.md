# ETL operational runbook

Run from repository root with Python 3.12 and dependencies installed via `pip install -e ".[dev]"`.
Configure a local ignored `.env`; never paste credentials into commands/reports. Native PostgreSQL
17.11 is the local server; unchanged Docker Compose is an alternative, not locally verified.

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate_db
.\.venv\Scripts\python.exe -m scripts.seed_master_data
.\.venv\Scripts\python.exe -m scripts.generate_legacy
.\.venv\Scripts\python.exe -m scripts.run_etl run
.\.venv\Scripts\python.exe -m scripts.run_etl summary
.\.venv\Scripts\python.exe -m scripts.run_etl reconcile
.\.venv\Scripts\python.exe -m scripts.run_etl snapshot
.\.venv\Scripts\python.exe -m scripts.run_etl run
.\.venv\Scripts\python.exe -m scripts.run_etl snapshot
.\.venv\Scripts\python.exe -m scripts.run_etl trace --order SO-0001
```

Generation is also the reset command: it replaces only the six named files and manifest under
`--output` (default data/legacy). Back up manual source corrections first. It never clears trusted
records or audits. Fixed seed 20261003 and frozen XLSX metadata/ZIP times make bytes repeatable.

`run --source sales` runs one department; other choices are purchasing, inventory, production,
quality and dispatch. Dependencies must already be loaded. `--root` selects another fixture
folder; `--quarantine` selects an evidence folder. `summary`, `reconcile` and `export` accept
`--run ETL-...`; without it they use the latest audit run. Failed runs may lack summary files;
inspect `summary` first, then use `export` for database-backed rejection details.

First pristine complete load: 464 extracted = 416 accepted + 48 rejected; 944 target rows inserted.
Replay: same accepted/rejected counts, 0 target inserts. Masters remain 36 rows. New execution
IDs/issues are intentional; compare the business snapshot instead of all-database row counts.

To demonstrate correction, copy the fixtures, correct sales row BAD-SALES-7 quantity from 0 to
100 locally using SQLite, then run `run --source sales --root <copy>`. The corrected row keeps
its unique source/business keys, producing 49 accepted / 7 rejected and two new target rows.
Changing already accepted SALE-0001 instead produces REPLAY_CONFLICT. Tests exercise both flows.

Successful-run counters count source rows; `inserted_targets` counts table rows. Fatal source
errors roll back the business transaction and preserve a failed run. Fix the source/header and
rerun. Export failure happens after commit: inspect failed status, run `export`, restore directory
access, then replay. A killed process may leave `running`; reconcile before changing status.
Never reset the database or truncate audit history as a recovery shortcut.

Alembic baseline: `scripts.migrate_db` creates an empty DB's schema or verifies an existing Phase 1
schema before stamping 0001_phase1. It does not recreate existing tables. Future revisions must
use reviewed explicit migrations; the baseline SQL is frozen and must not follow model edits.
Baseline downgrade is disabled to prevent accidental data loss. Do not blindly stamp divergent
schemas. Database CREATE privilege is needed for the opt-in test schemas.
