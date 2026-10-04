# Phase 2 validation report

Validated on 2026-10-03 against native Windows PostgreSQL 17.11. All source/business data is
synthetic. Phase 1 models, seed records, production API and Docker definition are preserved.

## VERIFIED

- Generated the six requested SQLite/CSV/Excel sources and an exact defect manifest with
  fixed seed 20261003. Tests verify byte-identical output across separate directories and resets.
- Implemented separate extract, normalize/validate, load, audit/quarantine and reconciliation
  modules; no forecasting, reorder, production scheduling, UI or Power BI work was added.
- Adopted existing Phase 1 schema with Alembic revision 0001_phase1 after reflection checks.
  No operational tables were rebuilt. A live isolated-schema test executes the frozen baseline
  from empty and verifies all 23 tables plus the Alembic version table.
- Existing schema/master verifier passed before ETL; the original 36-row data fingerprint was
  still `4b3f22d54c000aa5e4ac115b7eeeb5745ab5e81ce32260030b871149a77e4361` after adoption.
- Two real complete ETL runs succeeded; original master records remained byte-equivalent under
  canonical serialization. Both runs and all 96 rejection issues were verified in PostgreSQL.
- Quarantine files contain 48 inspectable rejected records per run, each matching the manifest's
  department, row position and expected rule. Raw contract values, timestamps and reasons persist.
- Reconciliation verifies accepted target fields, audit arithmetic, quarantine identities, file
  hashes, independently re-read source totals and target totals. No mismatches were found.
- The repeat-run business snapshot (including timestamps, excluding audit tables) was identical:
  `1a99a4e86ed0b968a9e1bd20626014e1f0c7182c42146d19e2d68f95f9ba9883`.
- All Phase 1 tests remain enabled and unchanged. Default tests need no PostgreSQL; live test
  variants use rolled-back isolated schemas. No temporary PostgreSQL test schemas remained.
- Ruff lint and formatting passed. Dependency check found no broken requirements. `.env` and
  generated quarantine directories remain ignored by Git; credentials were not printed.

## NOT VERIFIED / deliberately outside scope

Docker Compose runtime is not locally verified because hardware virtualization is disabled.
The unchanged Compose option remains available. No distributed/concurrent-writer stress test,
large-volume performance benchmark, production deployment, auth system or operational planning
algorithm is claimed. The runbook describes crash/export recovery and snapshot limitations.
A killed process can leave a `running` audit row. A database outage may prevent audit persistence.

## Data generated and ETL results

| Source | Format | Extracted | Accepted | Rejected | First-load target rows |
|---|---|---:|---:|---:|---:|
| Sales | SQLite | 56 | 48 | 8 | 96 |
| Purchasing | Excel | 200 | 192 | 8 | 384 |
| Inventory | CSV | 40 | 32 | 8 | 32 |
| Production | CSV | 56 | 48 | 8 | 288 |
| Quality | Excel | 56 | 48 | 8 | 48 |
| Dispatch | CSV | 56 | 48 | 8 | 96 |
| Total | | 464 | 416 | 48 | 944 |

The second run accepts the same 416 source rows but inserts **zero** target rows. Successful
source rows include unchanged replay, so accepted count is not an insert count. The database
contains 980 business/master rows (944 operational + 36 master), plus 2 run and 96 issue records.
Migration version bookkeeping is separate. No inventory ledger movements or planning rows
are fabricated. Stock exports are independent snapshots, not inferred receipts/issues.

First run: ETL-0640e67c8f5d467db1e80fbe6022e1b0

Second run: ETL-ad53da1581b844048ad063d3dfe23e57

Full machine-readable evidence: [phase2-live.json](evidence/phase2-live.json).
Local detailed receipts/rejections: `data/quarantine/<run-code>/` (Git-ignored).

## Intentional data-quality issues

Each source appends eight deliberate bad rows to its valid records. Three common defects are
repeated source ID, duplicate business key and missing record ID. Five additional defects per
source cover missing customer/supplier/warehouse references, unknown master codes, orphan order
or batch references, malformed dates, due/ship dates before prerequisite dates, zero/negative/
nonfinite quantities, unsupported units, missing QC measurements and invalid statuses.

The exact 48 row positions, keys, mutations and expected first-failure rules are recorded in
[data/legacy/manifest.json](../data/legacy/manifest.json). Correctable case/whitespace, RM code
variants and grams-to-kg conversions remain accepted, demonstrating cleaning as well as rejection.

## Reconciliation and traceability

All seven independent quantity comparisons matched: sales 9,200 kg; purchases 9,200 kg;
production planned output 9,200 kg; actual batches 9,200 kg; material consumption 9,200 kg;
shipments 9,200 kg; inventory snapshots 16,000 kg. These measures overlap and must not be added
together as one business total. Reconciliation checked 944 accepted target receipts.

`SO-0001` / customer `SYN-CUS-001` -> product `SYN-FG-001` -> production order/batch
`BATCH-0001` -> passed QC -> materials `SYN-RM-001` through `SYN-RM-004`, 25 kg each ->
purchase orders `PO-0001-1` through `PO-0001-4` -> suppliers `SYN-SUP-001`, `002`, `003`, `001`.
The four supplier lot codes are explicit synthetic source values. No proprietary formulation
or inferred operational consumption was used.

## Final test results

- `pytest -q --tb=short`: **49 passed, 1 skipped, 1 warning in 11.00s**. The skipped test is
  the explicit PostgreSQL-only baseline migration test.
- `pytest -q --postgres --tb=short`: **72 passed, 1 warning in 34.46s**.
- `ruff check .`: **All checks passed!**
- `ruff format --check .`: **61 files already formatted**.
- `pip check`: **No broken requirements found.**

Coverage includes extractors, byte determinism, normalization, all manifested defects, source
references, audit/issue counts, quarantine contents, corrected rejected-row replay, accepted-row
conflicts, idempotency, real PostgreSQL writes/rollback, fatal extraction, post-commit export
failure/recovery, source/target reconciliation, target tampering and customer-to-supplier lineage.
The remaining warning is the previously known upstream Starlette/httpx deprecation.

## Issues found and fixed

1. Windows SQLite connections were not closed by their transaction context manager, preventing
   fixture file replacement. Explicit closing fixed the handle leak in extraction/generation.
2. Python 3.12 SQLite legacy transaction mode can release the first savepoint as a commit.
   The pipeline now explicitly begins its SQLite outer transaction; fatal rollback is tested.
3. Reusing the selected source list as run provenance collided with Phase 1's unique source-key
   constraint during replay. Run provenance now includes a unique execution identifier.
4. Added explicit consumption and supplier-lot source fields rather than imputing observations
   from a BOM. The synthetic source carries all operational quantities.
5. Fixed new-file style findings and Alembic path-separator configuration. No checks were weakened.

Initial failing test runs were development evidence, not successful verification. Final results
above include the fixes. No destructive DB recreation, schema redesign or seed reset occurred.

## Exact commands run

All Python invocations used `.\.venv\Scripts\python.exe` from the repository root.
The main executed entry points (including repeated validations after fixes) were:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m scripts.generate_legacy
.\.venv\Scripts\python.exe -m scripts.migrate_db
.\.venv\Scripts\python.exe -m scripts.verify_db
.\.venv\Scripts\python.exe -m scripts.run_etl run
.\.venv\Scripts\python.exe -m scripts.run_etl snapshot
.\.venv\Scripts\python.exe -m scripts.run_etl reconcile --run ETL-0640e67c8f5d467db1e80fbe6022e1b0
.\.venv\Scripts\python.exe -m scripts.run_etl run
.\.venv\Scripts\python.exe -m scripts.run_etl snapshot
.\.venv\Scripts\python.exe -m scripts.run_etl reconcile --run ETL-ad53da1581b844048ad063d3dfe23e57
.\.venv\Scripts\python.exe -m scripts.run_etl trace --order SO-0001
.\.venv\Scripts\python.exe -m scripts.run_etl summary --run ETL-ad53da1581b844048ad063d3dfe23e57
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q --postgres --tb=short
.\.venv\Scripts\python.exe -m ruff check . --fix
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
```

Targeted Ruff commands also ran on `etl`, `scripts`, `database/migrations`, the new tests and
reconciliation files while resolving findings. Inline Python through the same interpreter's
stdin compared master/business fingerprints, SQL audit counts and saved the JSON evidence.
Git `status --short`, `diff --check` and `check-ignore` used command-local safe-directory trust.
Because all repository files are still untracked, whitespace inspection separately covers new
text files. One known failed-generation staging directory was removed after verifying its
resolved path was directly inside data/legacy. No user data or remote repository was modified.

## Files changed

Updated the ETL package description and added `etl/contracts.py`, `extract.py`, `fixtures.py`, `transform.py`, `load.py`, `pipeline.py`,
`reconcile.py`; three CLI modules for generation, ETL and migration;
`alembic.ini`, migration environment/template and frozen baseline SQL/revision;
`tests/test_etl.py`, `tests/test_migrations.py`; six fixture files and manifest; quarantine README;
runbook, ADR 002 and JSON evidence. Updated dependencies, ignore rules, README and business,
integration, data-quality, test/demo/roadmap documentation. The Phase 1 validation report remains
historical evidence. Operational models, seed logic and existing test assertions are unchanged.

## Recommended Phase 3 (not started)

With explicit approval, expose read-only operational APIs and stable analytics views over the
trusted data, with documented grains and reconciliation checks. Scope forecasting, reorder,
production scheduling and Power BI as later approved increments. Phase 2 ends here.
