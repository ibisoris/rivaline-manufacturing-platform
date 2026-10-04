# Phase 3 validation and final report

Validation date: 2026-10-04. All organisations, records and measurements are synthetic.
Phase 3 continued from the existing working tree; Phase 4 has not started.
Machine-readable results: [phase3-live.json](evidence/phase3-live.json).

## VERIFIED

Native PostgreSQL 17.11 is at Alembic revision `0002_reporting`. All 23 operational tables,
columns, nullability and primary/foreign/unique/check constraints still match the model.
All 36 Phase 1 master/BOM records and relationships are intact. Phase 2 business data remains
980 rows; including two ETL runs and 96 data-quality issues, total operational/audit rows are
1,078. No temporary test schemas remain. No live ETL reload was performed in Phase 3.

Before/after migration and live HTTP checks produced identical ordered snapshots:

- Business SHA-256: `1a99a4e86ed0b968a9e1bd20626014e1f0c7182c42146d19e2d68f95f9ba9883`.
  This also matches the Phase 2 evidence.
- All 23 tables, including audits: `2b71d22b48c0c0e1dcfe56226e3ba50590ec5b4389129064f9ba639d55b41ce9`.

The schema verification tool uses a different serialization and reports its own fingerprint;
these fingerprints must only be compared within the same snapshot implementation.
`.env` is ignored and is not tracked; no credential values were printed.

## API ENDPOINTS IMPLEMENTED

All business routes use `/api/v1`, GET only. Lists support bounded pagination and typed filters.
See [the full filter and response catalogue](19-api-and-analytics.md).

- `/products`, `/raw-materials`, `/suppliers`, `/customers`.
- `/inventory`, `/inventory/{inventory_id}`.
- `/sales-orders`, `/sales-orders/{order_id}`.
- `/purchase-orders`, `/production-orders`, `/production-batches`.
- `/quality-inspections`, `/shipments`, `/etl-runs`, `/data-quality-issues`.
- `/traceability/order/{order_id}`, `/kpis/operations`.

Existing `/health` is retained. OpenAPI describes 18 paths including health; documentation is
available at `/docs` and `/openapi.json`. Metadata version is 0.3.0. Responses use explicit
Pydantic schemas; Decimal quantities are strings. Missing details return 404, invalid filters
422, unsupported mutations 405, and database failures sanitized 503.

## ANALYTICS VIEWS IMPLEMENTED

| View | Grain | Live rows |
|---|---|---:|
| vw_inventory_position | Item/warehouse/lot | 32 |
| vw_order_fulfilment | Sales order line | 48 |
| vw_production_performance | Production order | 48 |
| vw_quality_performance | Inspection | 48 |
| vw_supplier_material_flow | Purchase order line | 192 |
| vw_data_quality_summary | Run/source/entity/rule/severity | 82 |
| vw_operations_kpis | All-time singleton | 1 |
| vw_operations_quantities | Metric/item type/unit | 10 |

Child rows are aggregated before joining. Purchase quantities are not presented as measured
receipts. View definitions and limitations are documented in the API catalogue.

## KPIs IMPLEMENTED

Shared reporting views supply API and future BI calculations. The [KPI dictionary](20-kpi-dictionary.md)
defines grains, statuses, denominators, units and exclusions.

Live synthetic results: 48 orders, 48 dispatched/delivered shipments, 48 production batches,
48 inspected batches and 48 fully passing batches: QC pass rate 100.000000%.
Two successful ETL executions, zero failed executions: 928 extracted, 832 accepted, 96 rejected;
acceptance 89.655172%, rejection 10.344828%; 96 recorded issues. ETL replay counts are explicitly
execution totals, not unique business records.

Sales ordered/shipped, production planned/actual, procurement ordered and material consumed each
report 9,200 kg in their respective metric/type group. Inventory on-hand and available each report
8,000 kg of product and 8,000 kg of raw material separately. Undefined rates are null; mixed units
are never added. These fixture values are not evidence of real operational improvement.

## TRACEABILITY DEMONSTRATION

Live `/api/v1/traceability/order/1` follows SO-0001, customer SYN-CUS-001 and product SYN-FG-001,
through its production order to BATCH-0001, passing quality inspection and linked shipment.
Four material consumption records of 25 kg each link to actual purchase lines/orders and supplier
lots; supplier codes are SYN-SUP-001, SYN-SUP-002, SYN-SUP-003 and SYN-SUP-001.
Full nested response is retained in the evidence JSON. The service uses real foreign keys rather
than inferred preferred suppliers. Automated tests cover missing downstream stages and assert
seven bulk SELECTs even when additional batches are present.

## MIGRATIONS

`0002_reporting` follows `0001_phase1` and creates the eight views without modifying operational
tables or data. Downgrade drops views in dependency order. PostgreSQL tests upgrade, downgrade and
reapply within an isolated schema while checking unchanged seeded records. The Phase 1 migration
test explicitly targets its original revision; its baseline assertions remain intact.
Existing unversioned schema adoption now verifies/stamps the baseline and then upgrades to head.
No additional indexes or dependencies were introduced.

## TEST RESULTS

| Executed check | Result |
|---|---|
| Default pytest | 52 passed, 2 skipped; 12.17 s |
| PostgreSQL-enabled pytest | 78 passed; 40.76 s |
| Targeted Phase 3 PostgreSQL tests | 6 passed; 17.27 s |
| Ruff lint | Passed |
| Ruff format check | 75 files already formatted |
| pip check | No broken requirements found |
| Native schema/master verification | Passed; no remaining test schemas |

Default skips are PostgreSQL migration checks. SQLite tests provide portability and logic evidence;
they do not substitute for PostgreSQL migration or read-only transaction verification. PostgreSQL
tests include READ ONLY and REPEATABLE READ transaction settings. Coverage includes filters,
pagination, details, 404/422, partial lineage, bounded query counts, view grains, multiple shipments,
batches and inspections, overshipment, failed ETL exclusion, zero denominators and mixed units.
Both suites report one existing Starlette/httpx TestClient deprecation warning.

## LIVE HTTP VALIDATION

A real Uvicorn subprocess ran locally on 127.0.0.1:18083 against native PostgreSQL, and was stopped
after verification. `/health`, `/docs`, `/openapi.json`, all 13 list routes, both detail routes,
traceability, KPI and a filtered/paginated product request returned 200. Unknown sales detail
returned 404; limit=201 returned 422; POST products returned 405. Evidence records every request
and status, list totals, complete trace, KPI values and view row counts.

## FILES CHANGED

Phase 3 additions/updates (the repository has no tracked baseline, so Git lists the project as
untracked; this is a phase-specific inventory, not a claim of a committed diff):

- `api/main.py`, `api/dependencies.py`, `api/routers/operations.py`.
- `api/schemas/filters.py`, `api/schemas/operations.py`.
- `api/services/__init__.py`, `api/services/operations.py`, `api/services/traceability.py`.
- `analytics/__init__.py`, `analytics/queries.py`.
- `database/migrations/versions/0002_reporting.py` and `0002_reporting.sql`.
- `scripts/migrate_db.py`, `scripts/verify_phase3.py`.
- `tests/test_api_analytics.py`, `tests/test_migrations.py`.
- `README.md`, `powerbi/README.md`, `docs/06-data-architecture.md`, `docs/09-security-rbac.md`,
  `docs/10-testing.md`, `docs/14-implementation-roadmap.md`, `docs/19-api-and-analytics.md`, `docs/20-kpi-dictionary.md`, this report,
  `docs/adr/003-read-only-information-layer.md`, `docs/evidence/phase3-live.json`.

## ISSUES/FIXES

Initial pagination test incorrectly assumed every list had at least two records; corrected to
respect the single-run test fixture while retaining total/order assertions. Ruff identified long
description lines, which were wrapped. The frozen baseline migration test now explicitly upgrades
to its baseline instead of the moving head. No Phase 1/2 business expectations were relaxed.
The environment's sandbox helper failed, so local commands required execution escalation.

## NOT VERIFIED / LIMITATIONS

This is an unauthenticated local synthetic-data prototype. Read-only transactions are enforced,
but the configured database role is not a deployed least-privilege production role. No internet
exposure, production security, concurrency/load benchmark or large-volume performance certification
was attempted. Trace responses are unpaginated; list pagination is capped at 200.
Docker was not validated because virtualization is disabled; native PostgreSQL was validated.
No external BI client or Power BI file was built or tested. Operational dates are limited to
recorded fields; actual production duration, measured goods receipts and supplier lead time cannot
be fabricated. Inventory is a source snapshot, not a reconstructed movement ledger.
No forecasting, reorder algorithm, scheduling, frontend or cloud deployment was implemented.
No changes were committed or pushed.

## EXACT COMMANDS RUN

From the repository root in PowerShell (all use the existing local virtual environment):

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_api_analytics.py
.venv\Scripts\python.exe -m pytest -q tests/test_api_analytics.py --postgres --tb=short
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q --postgres
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m scripts.verify_phase3
.venv\Scripts\python.exe -m scripts.verify_db
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform check-ignore .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform ls-files -- .env
```

The checked-in `scripts.verify_phase3` contains the exact reproducible live assertions and invokes
`python -m scripts.migrate_db` followed by `python -m scripts.run_api` using this virtual environment's
interpreter, with API_HOST=127.0.0.1 and API_PORT=18083 supplied only to its subprocess.
It requires the original two-run Phase 2 fixture, applies pending migrations, snapshots tables,
checks HTTP responses, writes evidence, and stops its server. It does not reseed or run ETL.
README's manual migrate/start/demo commands use the same entry points and operational routes.
The read-only HTTP probe set is recorded in the evidence JSON (plus the intentional rejected POST).

## RECOMMENDED PHASE 4

Seek explicit approval for a bounded decision-support phase: agree planning questions, required
history, units and evaluation baselines before implementing explainable demand/reorder logic.
Keep synthetic assumptions and backtesting limitations explicit. Power BI should consume the
stable reporting views and shared KPI definitions in its separately approved reporting phase.
Phase 4 has not begun.
