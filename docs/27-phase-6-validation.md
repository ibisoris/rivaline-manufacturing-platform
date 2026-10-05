# Phase 6 validation and final report

Completed 2026-10-05 (Europe/London), native PostgreSQL 17.11 and Python 3.12.2. Every business
record, resource, policy and result is synthetic. No commit or push was made. Phase 7 is not started.

Evidence: [before snapshot](evidence/phase6-before.json), [live results](evidence/phase6-live.json),
[planning contract](26-production-planning.md), [ADR 006](adr/006-production-planning.md).

## VERIFIED

Demand netting, deterministic batch sizing, pooled material feasibility, resource-month capacity,
whole-batch prioritisation, four planning APIs, five reporting views and optional immutable
forecast planning snapshots are implemented. Manual what-if remains computational/read-only.
All prior operational data, Phase 4 recommendations and Phase 5 forecasts are preserved.

Live verification applied the tested migration, checked seed/replay, calculated/saved/replayed the
forecast proposal, exercised nine isolated scenarios plus the real three-month forecast, started
FastAPI, made 16 HTTP checks, and stopped the temporary server. Native schema verification passed
for all 35 application tables, columns, nullability, keys and constraints. Zero test schemas remain.

## PLANNING GRAIN / ASSUMPTIONS

Product/month lines within one scenario/vintage; material detail per line/material; capacity per
resource/month. Forecasts and manual additional demand are separate modes. Stock is consumed
once across the horizon. Only allocated overproduction becomes later hypothetical surplus.
No unposted production supply is inferred; unmet demand is not silently rolled forward.

Existing confirmed sales commitments are protected in Phase 4 stock. Forecast planning rejects
outstanding confirmed sales because reliable forecast-consumption semantics are unavailable.
Manual input cannot claim to be a confirmed order. Reservations and existing requirements remain
conservatively additive; confirmed incoming is assumed wholly available at the horizon start.
Monthly hours are synthetic residual capacity after external commitments, not measured factory
availability. Feasibility is conditional on these assumptions. Full formulas are in document 26.

## DEMAND NETTING RESULTS

October and November forecast demand is entirely covered by existing finished stock. December:

| Product | Gross kg | Inventory offset kg | Net production kg |
|---|---:|---:|---:|
| SYN-FG-001 | 777.333333 | 445.333334 | 331.999999 |
| SYN-FG-002 | 948.000000 | 104.000000 | 844.000000 |
| SYN-FG-003 | 466.000000 | 466.000000 | 0 |
| SYN-FG-004 | 653.666667 | 653.666667 | 0 |

Horizon gross demand 8,535.000000 kg minus stock offset 7,359.000001 kg = net 1,175.999999 kg.
No prior batch surplus is needed in this forecast case. Six-decimal totals preserve the stored
Phase 5 quantities rather than rounding them away for presentation.

## BATCH PLAN

Synthetic policies: minimum 200, preferred 1,000, maximum 1,200 kg; processing rate 100 kg/hour.
December proposes one 331.999999 kg batch of FG-001 and one 844 kg batch of FG-002.
No batches are needed in the other ten product/month lines.

Isolated scenarios prove 2,300 kg -> [1,000,1,000,300] and 2,100 kg -> [1,000,1,000,200]. The latter
proposes 2,200 kg because the 100 kg tail is raised to the minimum. Tests enforce maximum bounds
and carry only allocated surplus forward. Batch records in these outputs are computational,
never inserted into the operational production_batches table.

## MATERIAL FEASIBILITY

The original BOM ratios are reused: each product uses 25 kg of each synthetic component per
100 kg output. Summing batch-level six-place explosions, each of RM-001 through RM-004 requires
294.000000 kg for the complete forecast proposal. Each starts with 2,000 kg available; material
shortage is zero. Allocation accepts only FG-001's batch, reserving a hypothetical 83 kg per
material; 1,917 kg remains in the scenario pool. No inventory row or transaction changes.

The material-only scenario needs 250 kg/component against 100 available, exposing 150 kg shortage
per component with sufficient hours. The combined scenario needs 375 against 100, exposing
275 kg shortage/component and a five-hour capacity overload.

## CAPACITY MODEL

Two compatible-resource groups: FG-001/002 use SYN-MIX; FG-003/004 use SYN-FILL. Each has 10 residual
hours per month. No sequential mixing-and-filling route is inferred. Capacity hours are repeated
per month but material and finished-stock pools are carried across the horizon.
Required batch hours = quantity / 100, conservatively rounded upward to six places. Utilisation
is proposed required / available * 100, shown to two decimals; zero capacity gives null.

## CAPACITY RESULTS

December mixing requires **11.76 hours** against **10**, utilisation **117.60%**, overload **1.76 hours**.
FG-001 takes 3.32 hours first. Its remaining 6.68 hours cannot fit FG-002's whole 8.44-hour batch,
so FG-002 is capacity-constrained with 844 kg unmet. The unused 6.68 hours demonstrate the cost
of whole-batch greedy allocation; this is not claimed to be an optimal schedule.

Across six resource/month cells, capacity is 60 hours, required 11.76, allocated 3.32, and aggregate
utilisation 19.60%. That low horizon average does not remove the December mixing bottleneck.
Resource-month overload sums to 1.76 hours. No workload is transferred between months/resources.

## CONSTRAINT DEMONSTRATIONS

Cases 1-8 and 10 use separate synthetic stock/policies in a temporary PostgreSQL schema rolled
back after evaluation. No historical public-schema records are edited for demonstrations.

| Case | Gross kg / setup | Expected and verified outcome |
|---|---|---|
| 1 Inventory covered | FG-001 1,000; stock 2,000 | FEASIBLE, zero batches/hours |
| 2 Production feasible | 2,500; stock 2,000; materials 2,000; 10h | Net/batch 500; 5h; FEASIBLE |
| 3 Material only | 3,000; materials 100; 10h | Batch 1,000; 150kg/component shortage; MATERIAL_CONSTRAINED |
| 4 Capacity only | 3,500; materials 2,000; 10h | Batches 1,000+500; 15h; CAPACITY_CONSTRAINED |
| 5 Combined | 3,500; materials 100; 10h | 275kg/component shortage and 5h overload; MATERIAL_AND_CAPACITY_CONSTRAINED |
| 6 Partial final batch | 4,300; 30h | Net 2,300 -> 1,000+1,000+300; FEASIBLE |
| 7 Minimum adjustment | 4,100; 30h | Net 2,100 -> 1,000+1,000+200; 100kg surplus; FEASIBLE |
| 8 Competing products | FG-001/002 each 2,800; shared 10h | Each net 800/8h; FG-001 allocated, FG-002 constrained |
| 9 Forecast horizon | Existing October-December 2026 forecast | 12 lines; 11 feasible, December FG-002 constrained |
| 10 What-if new constraint | FG-001 5,000 instead of feasible 2,500 | Net 3,000; 30h; capacity-constrained |

Additional tests cover zero capacity, unit/missing-policy/BOM errors, duplicate demand rejection,
firm/forecast overlap rejection, chronology, deterministic ties, shared materials across resources
and months, reservations/incoming/received purchase semantics, replay conflicts and database bounds.

## PRIORITISATION

Earlier month, ascending documented product priority, then product code. Input ordering does not
change the plan. Within each line, batches are considered in sequence; only whole batches with
both materials and hours allocate. A later smaller batch can fit after a larger one is rejected.

In the competing-products case, FG-001 (priority 1) consumes 8 of 10 mixing hours, leaving 2;
FG-002 (priority 2) needs 8, is unallocated and exposes the reason. Combined proposed load is 16h,
160% utilisation and 6h overload. A tie-priority test proves the product-code tie-breaker.
This avoids opaque scoring and does not claim globally optimal economic allocation.

## WHAT-IF DEMONSTRATION

Live POST `/api/v1/planning/production-plan/what-if` submitted FG-001 additional demand 5,000 kg,
2026-11-01, kg. It returned stock offset 2,000; net/proposed 3,000; three 1,000 kg batches;
750 kg/component requirement; zero material shortage; 30h required against 10; 300% utilisation;
20h overload; CAPACITY_CONSTRAINED. One whole batch allocates, leaving 2,000 kg unmet.

The response equals the CLI calculation. HTTP uses PostgreSQL READ ONLY / REPEATABLE READ.
Before/after snapshots and automated complete-table snapshots confirm no orders, batches,
purchases, inventory transactions, plan runs or other records were created by what-if requests.

## FORECAST-TO-PRODUCTION DEMONSTRATION

Phase 5 run `1e8d547d27460bb77d408e542c17682cd11ea6b745bd4dd898ec6d34b135464e` flows through
netting, batches, existing BOM, material allocation and shared capacity into the proposed plan.
One saved decision-support run:

`3ecf5b0a02aec4c3b39893468a2177d0730566849d67dfae82ec784fcee5828c`

Algorithm production-plan-v1; generated at `2026-10-04T22:14:15.925356+00:00`.
Replay returns created=false, the same timestamp/inputs/report and no added rows. Calculation
and saved reporting evidence match. Changed-input tests create separate snapshots while retaining
the original. Tampered/incomplete normalized material/report rows are rejected on replay.

## PLANNING KPIs

| KPI | Synthetic measured result / grain |
|---|---|
| Gross / stock offset / net | 8,535.000000 / 7,359.000001 / 1,175.999999 kg, horizon |
| Proposed / allocated / unmet | 1,175.999999 / 331.999999 / 844.000000 kg |
| Proposed batches | 2 |
| Material requirement / shortage | 294 kg / 0 per each of four materials |
| Allocated component quantity | 83 kg per material |
| Required / available / allocated capacity | 11.76 / 60 / 3.32 hours, six resource-month cells |
| December mixing utilisation / overload | 117.60% / 1.76h |
| Horizon utilisation | 19.60%; does not conceal the period/resource bottleneck |
| Constrained / feasible products | 1 / 3; a product is constrained if any month is constrained |
| Feasible-plan percentage | 11/12 product-month lines = 91.67% |

Values are prototype decision-support measures, not measured time savings or business impact.
Material availability and per-line capacity availability are not additive; use their documented
resource/material grains. Evidence JSON retains full inputs, outputs and scenario explanations.

## API ENDPOINTS

Added under `/api/v1/planning`: GET `/production-plan`, POST `/production-plan/what-if`,
GET `/capacity`, GET `/constraints`. Typed filters include required forecast_run_code, product,
month and status; pagination retains the established 50 default/200 maximum. Allocation precedes
filtering. Capacity filters retain competing products' resource totals.

Live server on 127.0.0.1:18086 returned 200 for health, Swagger, OpenAPI, all new routes, filters
and old KPI/trace/inventory/reorder/forecast endpoints; invalid pagination returned 422 and
unknown forecast returned 404. The server was stopped. OpenAPI has 31 paths, metadata 0.6.0.
Tests cover broader validation/404 cases and unchanged old GET-only contracts, with exactly one
new computational POST. No authentication or frontend is introduced.

## REPORTING VIEWS

| View | Grain | Live rows |
|---|---|---:|
| vw_production_plan | Plan run/product/month | 12 |
| vw_capacity_utilisation | Plan run/resource/month | 6 |
| vw_planning_constraints | Constrained plan run/product/month | 1 |
| vw_forecast_to_production | Plan run/forecast run/product/month | 12 |
| vw_planning_materials | Plan run/product/month/material | 8 |

The 15 prior views are unchanged; total 20. Views expose frozen snapshots for later Power BI,
not current-stock joins and not approved schedules. No dashboard files are created.

## MIGRATIONS

`0006_production` adds six tables: production_resources, production_policies, production_plan_runs,
production_plan_lines, production_capacity_results, production_material_results, and five views.
No existing table contract or applied Phase 1-5 migration is altered. Public database is at this
revision, 35 application tables plus Alembic bookkeeping. Real PostgreSQL tests check metadata
equality, original-data preservation, upgrade, configuration-only downgrade and reapplication.
Populated-run downgrade is explicitly rejected to protect planning evidence.

## TEST RESULTS

| Check | Final executed result |
|---|---|
| Full default pytest | 95 passed, 5 skipped, 1 warning in 17.48s |
| Full PostgreSQL-enabled pytest | 156 passed, 1 warning in 92.94s |
| Ruff lint | Passed |
| Ruff format | Passed |
| pip check | No broken requirements found |
| Live verifier | Passed; original fingerprint unchanged, 16 HTTP checks |
| Native schema/master verifier | Passed; 35 tables, 1,497 rows, no temporary test schemas |

Default skips are native migration tests. SQLite evidence is portability testing; native
PostgreSQL variants and live checks separately establish PostgreSQL behavior. The existing
Starlette/httpx TestClient deprecation warning remains. No tests were removed or disabled.
Historical migration tests remain pinned to their own revisions; current schema/OpenAPI inventory
expectations were extended explicitly.

## DATA PRESERVATION

All 29 Phase 1-5 tables and all 1,464 pre-existing rows match exactly, including timestamps,
source keys, ETL evidence, Phase 4 proposals and Phase 5 forecast/evaluation data:

`f8031cd35b26b041082aab74e464de1f5dc97d3807e23a046f815410a2b971f1`

New rows: 2 resources + 4 policies + 1 plan run + 12 lines + 6 capacity results + 8 material
results = 33; total 1,497. There was no operational ETL reload or fixture rewrite. Phase 3 KPI
and trace HTTP JSON equal saved Phase 3 evidence; Phase 4 stock positions equal saved evidence.
Live saved recommendations remain two and forecasts remain twelve with thirty evaluation metrics.
Tests additionally compare whole-database snapshots around computation/HTTP what-if.

## FILES CHANGED

Modified: README.md; api/main.py; database/models.py; docs/20-kpi-dictionary.md;
planning/__init__.py; tests/test_api_analytics.py, tests/test_forecasting.py,
tests/test_foundation.py, tests/test_planning.py.

Added: api/routers/production.py; planning/production.py, planning/production_contracts.py;
database/migrations/versions/0006_production.py, 0006_production.sql, 0006_tables.sql;
scripts/run_production.py, scripts/verify_phase6.py; tests/test_production.py;
docs/26-production-planning.md, docs/27-phase-6-validation.md;
docs/adr/006-production-planning.md; docs/evidence/phase6-before.json, phase6-live.json.

## GIT STATUS

Branch main. Phase 1-5 checkpoint remains `eb0e4c2ff587ec19361e7bbaac2e81734b03b323` with message
`feat: build integrated manufacturing data platform through forecasting`. Remote origin exists.
Phase 6 changes are unstaged: nine modified files and fourteen untracked project files.
No commit, amendment, push, repository creation or Phase 7 implementation was performed.
`.env` remains ignored and untracked. No credentials are included in project changes.

## ISSUES/FIXES

Initial assertions compared two rounded utilisation values with unrounded quotients and omitted
0.000001 kg from the stored forecast's stock offset. Corrected expected values to the documented
precision. No production arithmetic was weakened to satisfy tests.

Live replay initially compared equivalent timestamp strings with different UTC/local offsets.
The CLI now consistently serializes generation time in UTC. The first snapshot remains intact;
resumed verification reuses it, with no duplicate run. The final evidence therefore records a
replay rather than pretending its resumed seed/save calls created the original records.

The old OpenAPI test assumed every route was GET-only. It now explicitly requires POST only for
the authorized what-if path and still requires GET for every other route. A new missing-active-BOM
test initially used invalid status inactive; corrected it to the existing retired contract.
Ruff formatting/import findings were resolved. Windows sandbox startup failure required approved
execution outside the sandbox; no global Git configuration or database roles were changed.

## LIMITATIONS

No governed firm/forecast consumption, dated receipts/partial receiving, precise reservations,
warehouse transfers, QC/expiry availability, routing/cleaning/yield, shift calendars or workload
integration. Residual hours and undated incoming are explicit conditional assumptions. Greedy
whole-batch allocation can leave idle capacity and does not optimise economics or due dates.
Input/schema validation prevents silent gaps; unsupported forecast overlap fails rather than
inventing a demand interpretation. No automatic order release/purchasing or operational writes.

Local unauthenticated prototype; single-process snapshot writer; no load/concurrency certification.
Docker remains unverified because virtualization is disabled. No proprietary data, cloud deployment,
Power BI connection or dashboard. Forecast accuracy limitations from Phase 5 remain unchanged.

## EXACT COMMANDS RUN

From the existing project virtual environment, with command-local Git safe-directory configuration:

```powershell
.venv\Scripts\python.exe -m ruff check . --fix
.venv\Scripts\python.exe -m ruff format tests/test_production.py planning/production.py database/models.py tests/test_forecasting.py
.venv\Scripts\python.exe -m ruff format scripts/verify_phase6.py
.venv\Scripts\python.exe -m pytest -q tests/test_production.py --tb=short
.venv\Scripts\python.exe -m pytest -q tests/test_production.py --postgres --tb=short
.venv\Scripts\python.exe -m pytest -q --tb=short
.venv\Scripts\python.exe -m pytest -q --postgres --tb=short
.venv\Scripts\python.exe -m scripts.verify_phase6
.venv\Scripts\python.exe -m scripts.verify_db
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform diff --check
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform check-ignore .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform ls-files -- .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform branch --show-current
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform log -1 --format='%H %s'
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform remote
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform status --short
```

`verify_phase6` invokes scripts.migrate_db; scripts.run_production seed-policies twice, forecast,
save-forecast twice and what-if with the exact recorded forecast code/FG-001/2026-11-01/5000/kg.
It invokes scripts.run_api with process-only API_HOST=127.0.0.1 and API_PORT=18086, calls the routes
recorded in evidence via urllib, then terminates it. Inline Python captured the pre-change snapshot,
summarized KPI evidence and checked changed-file whitespace/credential patterns without printing
secret values. Initial targeted Ruff check/format commands were also used during implementation.
No dependency installation, Git staging/commit/push, operational reload or Phase 7 work occurred.

## RECOMMENDED PHASE 7

After review and explicit approval, connect Power BI to the stable reporting views. Require a
single plan/forecast vintage filter, separate product/month and resource/month grains, surface
material/capacity assumptions and distinguish proposed from allocated production. Show December's
resource bottleneck alongside horizon totals. Do not imply approved schedules or measured business
benefits. Phase 7 has not begun; no dashboard assets were created.
