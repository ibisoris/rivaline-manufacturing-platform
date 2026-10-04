# Phase 4 validation and final report

Validated 2026-10-04 on Windows, Python 3.12.2, native PostgreSQL 17.11. All data is synthetic.
Phase 4 is complete; no Phase 5 work was undertaken.

## VERIFIED

Inventory intelligence, BOM material requirements, rule-based reorder proposals, input snapshots,
read-only what-if, five API routes, three reporting views and deterministic evaluation are implemented.
The existing modular monolith, original operational tables, Phase 3 APIs and reporting definitions
remain intact. No purchase orders, forecasts or schedules were generated.

Evidence: [initial Phase 4 application](evidence/phase4-initial.json),
[final live checks](evidence/phase4-live.json), [calculation contract](22-inventory-and-reorder.md).

## PLANNING POLICY / ASSUMPTIONS

Four deterministic raw-material policies were inserted; repeat seeding inserted zero. Safety,
reorder, target and MOQ values are documented in document 22. All use kg and SYN-WH-RAW as the
proposed delivery destination. That destination does not restrict the pooled inventory calculation.

Stock is pooled across warehouses. Reservations and known requirements are conservatively additive
because no allocation linkage exists. Whole confirmed purchase lines are assumed outstanding;
no partial receipts or delivery guarantee is invented. Completed production and received purchases
contribute no future requirement/incoming supply. Product demand is outstanding confirmed sales;
it is not also exploded into production. Policy data is illustrative, not empirically optimized.

## INVENTORY CALCULATION

`available = on_hand - reserved`.
`projected = available + assumed_confirmed_incoming - required`.
`shortage = max(0, -projected)`.

Eight item positions are returned: four products and four raw materials. Each has 2,000 kg
on hand/available in the preserved fixture. Current reservations, outstanding confirmed sales,
open-production material needs and confirmed incoming quantities are all zero.
Raw-material risks: RM-001 healthy; RM-002 below_reorder; RM-003 below_safety; RM-004 at_reorder.
Products have no purchasing policy and return null reorder quantities.

## MATERIAL REQUIREMENTS RESULTS

Existing requirement grain is production order / BOM material. Gross quantity is planned product
quantity times BOM component/output ratio, rounded to six decimals. Recorded material consumption
is deducted and remaining requirement floored at zero. Consumption, lots and purchasing are
aggregated independently to avoid join multiplication.

The live fixture has 48 completed production orders, so zero outstanding material-requirement rows
is correct. Deterministic isolated tests create planned/released production and assert exact BOM
requirements, partial consumption, status exclusions, unit handling and fractional arithmetic.
Missing BOM lines fail closed; direct reporting also flags incomplete BOMs and suppresses proposals.

## REORDER RESULTS

If projected stock is below reorder point, propose max(target - projected, MOQ); otherwise zero.
Only positive proposals are persisted. Current native PostgreSQL results:

| Material | Projected kg | Trigger kg | Target kg | MOQ kg | Proposal kg |
|---|---:|---:|---:|---:|---:|
| SYN-RM-001 | 2000 | 500 | 1000 | 100 | 0 |
| SYN-RM-002 | 2000 | 2500 | 3000 | 100 | 1000 |
| SYN-RM-003 | 2000 | 2400 | 3000 | 1500 | 1500 |
| SYN-RM-004 | 2000 | 2000 | 3000 | 100 | 0 |

Exactly two proposed recommendation rows and one planning run exist. Run code:
`1c3d3c88cf4748221f07242d42a5599b4638fc96dad4ad223c37551f1de71e65`.
Generated at `2026-10-04T16:35:02.681299+00:00`.

Repeated calculations, including after the corrective migration, returned the same run with
created=false and retained its timestamp and proposal IDs. Structured inputs and plain-language
reasons are exposed on each proposal. Tests verify changed inputs create history, identical replay
preserves dismissed status, and restoring old inputs returns the original run. CLI transactions
save run/proposals atomically; no purchase order is created.

## WHAT-IF DEMONSTRATION

Actual GET request:
`/api/v1/planning/material-availability?product_id=1&quantity=10000&unit_of_measure=kg`.

The existing synthetic BOM contains four 25 kg component lines per 100 kg output. Additional
10,000 kg production needs 2,500 kg of each material. Each baseline projected position is 2,000 kg;
each scenario position becomes -500 kg, producing a new 500 kg shortage. Scenario reorder quantities
are 1,500 / 3,500 / 3,500 / 3,500 kg under the respective policies. The result says persisted=false.
Historical data, saved run inputs and proposal IDs were checked unchanged after HTTP execution.

## EVALUATION SCENARIOS

Common isolated policy: safety=20, reorder=50, target=100; all quantities kg. Expected results below
are hard-coded assertions, not generated expectations. Every case passed on SQLite and PostgreSQL.

| Scenario | Stock | Required | Incoming | MOQ | Expected projected | Expected shortage | Expected reorder |
|---|---:|---:|---:|---:|---:|---:|---:|
| Healthy | 100 | 0 | 0 | 0 | 100 | 0 | 0 |
| Below trigger | 40 | 0 | 0 | 0 | 40 | 0 | 60 |
| Existing requirement shortage | 30 | 80 | 0 | 0 | -50 | 50 | 150 |
| BOM exposes shortage: 400 product -> 100 material | 25 | 100 | 0 | 0 | -75 | 75 | 175 |
| Incoming removes shortage | 30 | 80 | 150 | 0 | 100 | 0 | 0 |
| MOQ controls proposal | 40 | 0 | 0 | 200 | 40 | 0 | 200 |
| Below safety | 10 | 0 | 0 | 0 | 10 | 0 | 90 |
| Exactly at trigger | 50 | 0 | 0 | 0 | 50 | 0 | 0 |
| Additional 800 product -> 200 material what-if | 100 | 200 incremental | 0 | 0 | -100 | 100 | 200 |

All nine scenarios met expected outcomes. Additional assertions cover reservations, multiple lots
and warehouses, partial material consumption, excluded purchase/production statuses, unit conflicts,
missing/ambiguous BOMs, fractional quantities, idempotency, immutable snapshots and policy conflicts.
These measure deterministic correctness, not stockout reduction or financial benefit.

## API ENDPOINTS

All use GET under `/api/v1`, explicit Pydantic responses, Decimal strings and existing read-only
transaction dependencies:

- `/inventory/positions`: item_type/item_id/shortage_only and pagination.
- `/planning/material-requirements`: material/production-order filters and pagination.
- `/planning/material-availability`: one product/quantity/unit and optional active BOM; no persistence.
- `/reorder-recommendations`: material/destination warehouse/status/run_code and pagination.
- `/reorder-recommendations/{id}`: saved inputs, explanation and affected production requirements.

Live HTTP: health/docs/OpenAPI, all five new routes, filtered requests, old trace and old KPI returned
200. Unknown proposal returned 404; limit=201 returned 422; unit mismatch returned 409. Automated
tests also verify rejected mutations, query validation and no what-if writes. OpenAPI has 23 paths
including health; metadata version 0.4.0. Temporary server used 127.0.0.1:18084 and was stopped.

## REPORTING VIEWS

- `vw_material_requirements`: open production order / raw material; live rows 0.
- `vw_inventory_risk`: pooled item type / ID; live rows 8.
- `vw_reorder_recommendations`: persisted proposal ID with run/version; live rows 2.

All eight Phase 3 views remain. Do not sum quantities across units, item types, metrics or historical
calculation runs. View grains and assumptions are documented for future Power BI consumption.

## MIGRATIONS

`0003_planning` adds planning_policies and planning_runs plus three views. Original 23 table
contracts are unchanged. `0004_fractional_bom` makes numeric division explicit in the requirements
view. Native PostgreSQL is at `0004_fractional_bom`. Actual PostgreSQL tests verify schema matches
SQLAlchemy metadata, upgrade/downgrade/reapplication, unchanged seed data, and refusal to drop
populated run history. No additional package dependency was required.

## TEST RESULTS

| Check | Executed result |
|---|---|
| Full default pytest | 65 passed, 3 skipped, 1 warning; 12.23 s |
| Full PostgreSQL-enabled pytest | 105 passed, 1 warning; 48.69 s |
| Ruff lint | All checks passed |
| Ruff format | Passed; all files formatted |
| pip check | No broken requirements found |
| Live HTTP, calculations and replay | Passed; JSON evidence linked above |
| Schema/master verifier | Passed; all 25 current tables checked; zero remaining test schemas |
| README positions/requirements CLI commands | Passed; 8 / 0 rows respectively |
| Git .env checks | Ignored; no tracked entry |

The three default skips are PostgreSQL migration checks. PostgreSQL-enabled tests include SQLite
portability variants and real PostgreSQL variants; no default test requires a running service.
The existing Starlette/httpx TestClient deprecation warning remains unsuppressed.

## DATA PRESERVATION

Pre-migration, post-migration and final historical-row fingerprints are identical and match Phase 3:
`2b71d22b48c0c0e1dcfe56226e3ba50590ec5b4389129064f9ba639d55b41ce9`.
This covers all 1,078 original business/audit rows, including timestamps and all 96 DQ issues.
All 36 master/BOM seed values and relationships also passed the independent schema/master verifier.
Phase 3 live trace and KPI JSON responses match saved Phase 3 evidence exactly.

Authorized additions are four policies, one run and two proposals: 1,085 total rows across 25 tables.
Historical fingerprinting excludes only the identified Phase 4 proposal additions and new tables;
it does not exclude changes to any original operational/audit row. Full-database verification
fingerprint after these additions is
`ebcac7e3653743a623a21de16bb875c8e9665a3f3c1fbc24034c7b518bc03582`.
No ETL reload, operational fixture rewrite or historical quantity/status edit was performed.

## FILES CHANGED

The repository remains entirely untracked with no committed baseline; this is the Phase 4 inventory:

- `database/models.py`; new migrations `0003_planning.py`, `0003_tables.sql`, `0003_planning.sql`,
  `0004_fractional_bom.py`, `0004_fractional_bom.sql`.
- `planning/__init__.py`, `planning/contracts.py`, `planning/inventory.py`, `planning/policies.py`.
- `api/main.py`, `api/routers/planning.py`.
- `scripts/run_planning.py`, `scripts/verify_phase4.py`, `scripts/migrate_db.py`, `scripts/verify_db.py`.
- `etl/reconcile.py`: retain the original-table snapshot scope as metadata grows.
- `tests/test_planning.py`, `tests/test_foundation.py`, `tests/test_migrations.py`,
  `tests/test_api_analytics.py`: new tests and explicit current-vs-frozen revision assertions.
- `README.md`, `powerbi/README.md`, docs 06/10/14/20/22/23, ADR 004,
  `docs/evidence/phase4-initial.json`, `docs/evidence/phase4-live.json`.

No secrets, commits, pushes, dashboard files or Phase 5 implementation were added.

## ISSUES/FIXES

A new fractional BOM test found SQLite integer-affinity division returned 33 instead of 33.333333.
PostgreSQL passed the case. Corrected via a separate follow-up view migration, preserving the
already-applied revision. Final full suites passed on both backends.

Updated the foundation table-set expectation to include two additions, pinned the Phase 3 migration
test to its own revision, and updated OpenAPI path/version expectations without relaxing existing
behavior assertions. Baseline checks still cover all original 23 tables. Corrected the schema
verifier's old hard-coded table-count message; its validation already iterated all current tables.
Ruff formatting findings were resolved. Sandbox process startup failed, so commands required
execution escalation. No global Git trust or database-role settings were changed.

## LIMITATIONS

Pooled stock assumes transferability; reservations may overlap requirements; confirmed incoming
assumes no partial receipt; snapshot timestamps do not prove current physical stock. Policies are
synthetic, with no demand variability, lead-time model or service-level calibration. No expiry/QC
allocation, warehouse scheduling, supplier selection or exact availability-to-promise is provided.

The local API has no authentication. Calculation writers are single-process; uniqueness rejects
concurrent duplicate writes but no stress test/distributed retry is supplied. Proposal history is
loaded before pagination, suitable for this bounded prototype. Docker is unverified because local
virtualization is disabled. No production deployment, Power BI client, purchasing integration,
forecasting or scheduling was implemented or verified.

## EXACT COMMANDS RUN

From the repository root, using the existing virtual environment:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_planning.py --tb=short
.venv\Scripts\python.exe -m pytest -q tests/test_planning.py --postgres --tb=short
.venv\Scripts\python.exe -m pytest -q --tb=short
.venv\Scripts\python.exe -m pytest -q --postgres --tb=short
.venv\Scripts\python.exe -m ruff check . --fix
.venv\Scripts\python.exe -m ruff format .
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m scripts.verify_phase4
.venv\Scripts\python.exe -m scripts.verify_db
.venv\Scripts\python.exe -m scripts.run_planning positions
.venv\Scripts\python.exe -m scripts.run_planning requirements
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform check-ignore .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform ls-files -- .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform status --short
```

`verify_phase4` was executed twice, initially for 0003 and then for 0004. It invokes the exact CLI
entry points `scripts.migrate_db`, `scripts.run_planning seed-policies` twice and
`scripts.run_planning calculate` twice, then starts/stops `scripts.run_api` with process-only
API_HOST=127.0.0.1 and API_PORT=18084. Its source contains all SQL/HTTP/assertion details; evidence
records every live route and result. Initial evidence was copied to phase4-initial.json before
writing final evidence. Scripts read local configuration without printing credentials.

## RECOMMENDED PHASE 5

Before any forecasting work, explicitly approve the scope, required synthetic history, evaluation
horizon and transparent baseline. Agree how forecasts would remain distinct from firm demand and
how allocations/receipts should constrain future planning. Production scheduling and dashboards
remain separate scope decisions. Phase 5 has not started.
