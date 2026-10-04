# Testing

`python -m pytest -q` runs Phase 1, Phase 2 and Phase 3 tests without requiring PostgreSQL.
`python -m pytest -q --postgres` adds live PostgreSQL variants and executes the frozen Alembic
baseline in a disposable schema. Transaction rollback removes all test schemas and data.

Phase 1 contracts remain tested: health, configuration, schema, seed and relational constraints.
Phase 2 covers byte-deterministic files/reset, all three extractors, identifier/date/decimal rules,
all manifested defects, source-level audit accounting, quarantine, idempotent replay, corrected
rejects, changed accepted rows, target tampering detection, failure rollback and export recovery.
A customer-order/product/batch/QC/consumption/supplier trace is asserted on both backends.
SQLite explicitly starts an outer transaction before row savepoints to avoid accidental commits
under Python 3.12's legacy SQLite transaction behaviour. The readers explicitly close connections
so Windows can replace fixture files.

Ruff validates formatting/imports/style; pip check validates dependency consistency. Actual
results are in `21-phase-3-validation.md`; Phase 2 evidence is in `17-phase-2-validation.md`; historical Phase 1 evidence remains in document 16.


Phase 3 adds typed API contract tests, pagination/filter validation, HTTP error handling,
full and partial bulk lineage, reporting grains, KPI edge cases and OpenAPI generation.
PostgreSQL checks reporting migration upgrade/downgrade/reapply and read-only request isolation.
The explicit `python -m scripts.verify_phase3` command applies migrations and runs real local
HTTP checks against the preserved two-run Phase 2 dataset; see document 21 for prerequisites.


Phase 4 adds deterministic inventory/BOM/reorder evaluation, input-unit conflicts, replay/history,
read-only what-if and migration preservation checks. `python -m scripts.verify_phase4` applies
pending migrations, seeds only planning policies, generates/replays proposals and performs real
HTTP checks against the preserved two-run legacy fixture. See documents 22 and 23.


Phase 5 tests deterministic archived demand, strict aggregation/missing-period rules, chronological
leakage prevention, all candidate models and metrics, deterministic selection, non-negative output,
replay/conflict/history behavior, APIs, reporting grains and forecast-to-BOM calculations. The
explicit scripts.verify_phase5 command checks native migration/data preservation and real HTTP.
See document 25 for executed results, not just planned coverage.
