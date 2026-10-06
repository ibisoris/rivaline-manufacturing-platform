# Phase 7 validation report

Final manual Desktop validation confirmed by the user on 2026-10-06. Automated baseline validated 2026-10-05 on the fictional Rivaline platform. Phase 1-6 checkpoint remains
`c3a09b903691b47d7f8a5bb2fff0211ff7a7cd14` on main as the parent checkpoint. This report accompanies the authorised Phase 7 local checkpoint; no push or later-phase work is authorised.

Evidence: [database baseline](evidence/phase7-before.json), [original Power BI artifact hashes](evidence/phase7-powerbi-baseline.json),
[live/static results](evidence/phase7-live.json), [architecture and demo](28-powerbi-management-intelligence.md).

## VERIFIED BY CODE

The user-generated PBIP/PBIR/TMDL project was inspected before generation. Power BI Desktop is
installed as Microsoft Store package 2.158.1177.0. Existing project references, platform identities,
compatibility 1606, culture, base theme and initial page identity were preserved. Original text
files were backed up locally; the binary PBIX remains unchanged and ignored.

- 76 project/report JSON documents pass schema checks: 14 against their exact pinned schema
  and 62 Desktop-saved visual containers via the explicit 2.12 structural compatibility check.
  Their declared 2.13 schema is unavailable (Microsoft URL returned 404); exact 2.13 conformance
  is not claimed. The saved artifacts are retained unchanged.
- Six pages and 62 generated visuals have unique IDs, in-canvas positions and valid model bindings.
- 21 model tables, 25 single-direction dimension/fact relationships and 39 measures have structural
  and binding checks. No ambiguous many-to-many or bidirectional relationship was introduced.
- Generation is deterministic and works without the ignored local backup; tests compare two
  independent generations byte-for-byte. Saved Desktop query bindings, positions, visual types
  and full M source blocks are compared with generated contracts, allowing only selection
  metadata, indentation and the known PBI_ResultType annotation. Extra visuals are rejected.
- Source/run parameters are explicit, nonsecret and filter a single forecast/reorder/plan vintage.
  Selected-model backtests use a distinct product/model join to prevent three-month duplication.
- Power Query expressions contain no credentials; .env, PBIX, local .pbi caches/settings and backups
  are ignored. Candidate secret scans found no local password, key or credential values.

These checks do not execute Power Query, parse TMDL in the native Desktop engine, evaluate DAX,
or render built-in visuals. Separate user-observed Desktop validation below confirms successful refresh and rendering.

## VERIFIED AGAINST POSTGRESQL

The native verifier uses REPEATABLE READ / READ ONLY and executes the same table, column, filter
and selected-model join contracts as the import model. It validates dimension uniqueness,
referential coverage and fact grains. It does not claim to run the M or DAX engine.

| Required example | Verified source result |
|---|---:|
| RM-002 proposed reorder | 1,000 kg |
| RM-003 proposed reorder | 1,500 kg |
| FG-001 October / November / December | 777.333333 kg each |
| FG-002 October / November / December | 948.000000 kg each |
| FG-003 October / November / December | 466.000000 kg each |
| FG-004 October / November / December | 653.666667 kg each |
| Selected-policy holdout observations | 12 |
| Selected-policy holdout MAE | 18.416667 kg |
| Selected-policy holdout RMSE | 23.973944 kg |
| Net production requirement | 1,175.999999 kg |
| December mixing required / available | 11.76 / 10 hours |
| December mixing utilisation | 117.60% |
| FG-002 constrained/unmet quantity | 844 kg |

The operations singleton remains 48 orders, 48 batches, 48 inspected/passed batches, 832 accepted
and 96 rejected ETL row events from 928 extracted events, and 96 data-quality issue observations.
All 19 imported entities read successfully from existing views/master dimensions. Selected imports
include 12 forecasts, 12 selected-model holdout observations, 12 plan lines, six capacity rows,
eight planning material rows and two reorder proposals. Complete row counts are in live evidence.

## USER-VERIFIED POWER BI DESKTOP RESULTS

The user reported successful opening of RivalineOperations.pbip, PostgreSQL authentication,
model refresh and rendering of all six report pages, with one visual error described below.
The user subsequently reopened and refreshed the PBIP after the targeted fix and confirmed
all six pages render with no visual-level data-fetch errors. The values below were confirmed
in that final inspection. These are user-observed results, not inferred from automated checks.

| Rendered KPI | User-verified value |
|---|---:|
| Orders | 48 |
| Materials at risk | 2 |
| Batch QC pass | 100% |
| Forecast demand | 8.535K kg |
| Selected-policy holdout MAE | 18.416667 kg |
| Selected-policy holdout RMSE | 23.973944 kg |
| Net production requirement | ~1,176 kg |
| Constrained production | 844 kg |
| December mixing required | 11.76 h |
| December mixing available | 10 h |
| ETL acceptance | 89.66% |
| ETL rejection | 10.34% |
| Data quality issues | 96 |

### Targeted rendering defect and fix (2026-10-06)

On **02 Inventory & Procurement**, the table **Supplier material flow | orders, not receipts**
(visual ID `0607f9894098bb09f1b4`) failed with:

> Could not resolve the QueryDefinition. The query contains at least two expressions in its
> select clause with identical native reference name 'code'.

The `Supplier[code]` and `Material[code]` projections both had `nativeQueryRef: "code"`.
Only those aliases in the PBIR visual and matching page manifest were changed to
`Supplier.code` and `Material.code`. The underlying field expressions, queryRef values,
Procurement Ordered kg measure, visual identity, layout and intended supplier/material
order breakdown are unchanged. No semantic-model, database, business-calculation or
Phase 1-6 application changes were required.

The generator now qualifies colliding native references using their existing queryRef.
The binding validator rejects duplicate native reference names across every visual's
query roles. A regression test restores the original collision in an isolated project
copy and requires validation to fail; deterministic generation verifies reproducibility.

Post-fix automated validation executed on 2026-10-06:

- `pytest -q tests/test_powerbi.py --postgres --tb=short`: **5 passed** (32.05s),
  including the collision regression, deterministic generation and read-only PostgreSQL
  reconciliation with before/after data preservation.
- `python -m scripts.validate_powerbi`: **passed**, 76 schema documents, 62 visuals,
  21 tables, 25 relationships and 39 measures; all visual native references unique.
- `ruff check .` and `ruff format --check .`: **passed**, 119 Python files formatted.

The full-suite results later in this document are the earlier Phase 7 baseline; the targeted
suite above was rerun for this binding-only fix. No commit or push was made.

**Final manual Power BI Desktop validation passed (user confirmation, 2026-10-06).**

After reopening and refreshing RivalineOperations.pbip, the user manually inspected:

- 01 Executive Operations: renders successfully.
- 02 Inventory & Procurement: renders successfully; the previously failing supplier material
  flow table now shows supplier, material and procurement ordered quantity correctly.
- 03 Demand & Forecasting: renders successfully.
- 04 Production & Capacity: renders successfully.
- 05 Quality & Data Trust: renders successfully.
- 06 Transformation & Value: renders successfully.

No visual-level data-fetch errors were observed. PostgreSQL authentication/refresh and the
visible KPI values above are confirmed. Navigation, accessibility or interaction tests beyond
this reported inspection are not independently claimed. The retained original PBIX is not the
new Phase 7 report.

## FILES CHANGED

Modified tracked files: .gitignore, README.md, powerbi/README.md and pyproject.toml (jsonschema is a
development validation dependency). No Phase 1-6 application, migration, planning or test file was
changed. The existing PostgreSQL/API behavior remains covered by the full regression suites.

New/reviewable source files:

- User-created RivalineOperations.pbip and original Report/SemanticModel textual metadata/theme,
  now extended with TMDL tables, parameters, relationships, measures and six PBIR report pages.
- powerbi/model-spec.json, page-spec.json, model-and-measures.md, page-build-specification.md.
- powerbi/templates/Calendar.tmdl and model.tmdl; pinned powerbi/schemas files, URL manifest,
  provenance README and upstream MIT license.
- scripts/build_powerbi.py, scripts/validate_powerbi.py, scripts/verify_phase7.py.
- tests/test_powerbi.py.
- docs/28-powerbi-management-intelligence.md and this Phase 7 report.
- docs/evidence/phase7-before.json, phase7-powerbi-baseline.json and phase7-live.json.

Ignored and retained locally: original RivalineOperations.pbix; both .pbi folders and their caches/
settings; .phase7-backup; existing .env, virtual environment, pytest/Ruff/bytecode caches and ETL
quarantine artifacts. They are not source-control candidates. No original user artifact was deleted.

## POWER BI MODEL

Five master/configuration dimensions (Product, Material, Supplier, Customer, Resource), fourteen
reporting entities, a Calendar dimension and a Metrics table. Import mode targets localhost:5432,
rivaline. Date/month filtering covers archive start through selected forecast horizon end. Relationships
are one-to-many, single-direction. Operations is an intentionally disconnected all-time singleton.

Supplier selection affects procurement only. Product selection does not remove shared resource
capacity. Resource selection filters Capacity and Production Plan; the material allocation detail
is explicitly labelled all-resource. Archive actuals, operational sales, forecast vintages and
saved production plans remain conceptually separate. See the full [model catalogue](../powerbi/model-and-measures.md).

## DAX/KPIs

Thirty-nine named measures cover orders/sales, material stock/risk/reorder, procurement orders,
archived demand/forecast, selected-model holdout variance/MAE/RMSE, net/proposed/allocated/unmet
production, material needs/shortages, resource hours/utilisation/overload, QC and ETL trust.
DIVIDE handles zero denominators; percentages are formatted fractions. Quantity units are explicit.
Holdout metrics pool actual selected-model errors, not candidate-level summary averages. Future
variance against absent actuals is not fabricated. Capacity uses the resource/month fact and
constrained quantity is unmet demand. Exact DAX/formats/descriptions are catalogued beside the model.

Power BI double/number preserves six-place inputs better than four-place fixed-decimal currency,
but is not arbitrary-precision Decimal. Native displayed results require the manual tolerances:
0.000001 for quantities/errors and 0.01 for displayed hours. PostgreSQL remains authoritative.

## REPORT PAGES

1. Executive Operations: headline all-time/current/snapshot KPIs, stock/capacity comparisons and
   management exceptions with the known December bottleneck clearly explained.
2. Inventory & Procurement: material/supplier controls, current/projected material stock, selected
   reorder proposals and supplier material orders (not measured receipts).
3. Demand & Forecasting: product control, archive/forward trend, selected model, selected-policy
   holdout accuracy and actual-versus-predicted holdout chart, monthly forecast detail.
4. Production & Capacity: net/unmet quantities, fixed labelled December mixing example cards,
   month/resource controls, capacity comparisons and detail, allocation/material detail. A labelled
   separate Phase 6 what-if reference explains 5,000kg FG-001 demand; the report submits no requests.
5. Quality & Data Trust: batch QC, inspection counts, weighted ETL rates and issue/source/rule lineage.
6. Transformation & Value: six-step journey from fragmented files to management decisions, supported
   project evidence and a concise interview/demo route without financial ROI claims.

The user confirmed all six pages and the corrected procurement table render successfully. Static reference narratives
are labelled synthetic/verified examples and must be reviewed when changing snapshot parameters.

## POSTGRESQL VIEWS

No new views or migrations. The model reuses vw_operations_kpis, vw_inventory_risk,
vw_reorder_recommendations, vw_order_fulfilment, vw_production_performance, vw_quality_performance,
vw_supplier_material_flow, vw_data_quality_summary, vw_demand_history, vw_demand_forecast,
vw_forecast_backtest, vw_production_plan, vw_capacity_utilisation and vw_planning_materials.

Small Product/Material/Supplier/Customer/Resource dimensions use their authoritative master tables;
operational facts use the trusted reporting views. The database remains at 0006_production, with
35 application tables and 20 existing views. No historical data was adjusted for visual appeal.

## TEST RESULTS

Final full-suite results are recorded below after execution. Default tests remain service-independent;
the new --postgres reconciliation additionally reads verified public data in a READ ONLY transaction.
All earlier PostgreSQL constraint/migration variants continue using their rollback-isolated schemas.

| Check | Final executed result |
|---|---|
| Default pytest | 98 passed, 6 skipped, 1 warning; 17.92s |
| PostgreSQL-enabled pytest | 160 passed, 1 warning; 109.86s |
| Targeted BI tests with PostgreSQL | 4 passed |
| Microsoft JSON schema / bindings / visual inventory | Passed: 76 documents, 62 visuals |
| Deterministic generation | Passed; byte-equivalent outputs |
| PostgreSQL reconciliation and preservation | Passed; all required examples and 1,497 rows |
| Ruff lint / format | Passed |
| pip check | No broken requirements found |
| git diff --check / candidate whitespace | Passed |
| Credential and ignored-artifact review | Passed; .env/PBIX/.pbi excluded |

The six default skips cover PostgreSQL migration/reconciliation checks. Native variants run only
with --postgres. The single warning is the pre-existing Starlette/httpx deprecation. Desktop round-trip tests now distinguish deterministic generator output from Desktop serialization,
while retaining business-binding and M-expression equality. No visual/DAX/refresh success is
inferred from automated results.

## DATA PRESERVATION

All 35 Phase 1-6 tables and 1,497 rows match before/after, including timestamps, ETL evidence,
recommendations, forecast metrics/backtests and production planning snapshots:

`328225ecb90dcbe82555c132c7a366068d424be834a2cc8691a168ebc6c0367c`

No data migrations, ETL reloads, reseeds, forecast runs or planning runs occurred. The original PBIX
hash matches the initial user-artifact manifest. Eleven original Power BI metadata/theme/culture/
reference/binary files were byte-verified unchanged; only the blank page/page-order and model
root were intentionally extended, alongside new definition files. .env remains ignored/untracked.
The authorised Phase 7 checkpoint adds reporting assets without altering the Phase 6 checkpoint or operational data.

## KNOWN LIMITATIONS / ISSUES RESOLVED

- JSON Schema conformance and static bindings are not native TMDL, M, DAX or visual-engine execution.
  Desktop open/refresh/render validation has separately passed by user confirmation. The installed server-library probe did not expose the
  documented TmdlSerializer, and no unsupported parser result was claimed.
- Theme metadata mentioned visual 2.13.0; the corresponding attempted visualContainer schema URL
  returned 404. Microsoft's published versions include 2.12.0, used for new visual containers
  with its exact dependencies. Existing report/project versions were preserved, not downgraded.
- A changed visual title generated a new ID and left one obsolete Phase 7-generated visual. The
  test correctly caught 63 instead of 62 visuals. Removed that one verified generated artifact
  and added exact page-manifest consistency validation; no user-created artifact was deleted.
- An initial broad file inspection included machine-local security-binding metadata. Subsequent
  inspection excludes .pbi entirely; it is ignored and no local metadata/password is included in
  the source assets. Credentials were never copied into M/TMDL or the report.
- Current stock and saved planning snapshots have different freshness; switching vintages requires
  explicit parameters and narrative review. The import model is not a live planning executor.
- Selecting future months can leave no holdout errors; do not display blank accuracy as zero.
  The Desktop acceptance guide describes optional interaction settings for accuracy cards.
- Residual capacity, undated incoming, conservative reservations and synthetic forecast limitations
  remain as documented in Phases 4-6. No actual financial ROI, OEE, delivery reliability or automatic
  purchasing/production release is supported. No cloud/service/gateway deployment is provided.
- The existing Starlette/httpx deprecation warning remains. Windows sandbox startup failed, so
  required execution used approved escalation. No database role or global Git setting was changed.

## EXACT COMMANDS RUN

```powershell
.venv\Scripts\python.exe -m pip install 'jsonschema>=4.23,<5'
.venv\Scripts\python.exe -m scripts.build_powerbi
.venv\Scripts\python.exe -m scripts.validate_powerbi
.venv\Scripts\python.exe -m scripts.verify_phase7
.venv\Scripts\python.exe -m pytest -q tests/test_powerbi.py --postgres --tb=short
.venv\Scripts\python.exe -m pytest -q --tb=short
.venv\Scripts\python.exe -m pytest -q --postgres --tb=short
.venv\Scripts\python.exe -m ruff format scripts/build_powerbi.py scripts/validate_powerbi.py
.venv\Scripts\python.exe -m ruff format scripts/verify_phase7.py tests/test_powerbi.py
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform diff --check
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform status --short
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform rev-parse HEAD
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform check-ignore .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform ls-files -- .env
```

Targeted Ruff --fix checks also ran on newly added scripts. Inline Python captured original artifact
hashes/database counts, downloaded the pinned official schema URLs and MIT license, inspected
PostgreSQL column contracts, built specifications/catalogues and scanned candidate files for
secrets/whitespace. The deterministic test invokes scripts.build_powerbi --output <pytest-temp-dir>.
Get-AppxPackage inspected the installed Desktop version; assembly reflection tested only parser
availability and did not open Power BI or access credentials. Original .pbi values were not used
by the generated assets. No Git staging, commit, push, Desktop refresh or later-phase work occurred.

Final Desktop validation is complete. The user authorised one local Phase 7 checkpoint with
message `feat: add validated Power BI operations dashboard`. No push or additional phase is started.


## FINAL CHECKPOINT VALIDATION (2026-10-06)

The first checkpoint test run exposed Desktop serialization differences, rather than a new
rendering defect: visual schema declarations became 2.13, Desktop saved active projections/page,
omitted default formatting properties, and reserialized TMDL with lineage tags and metadata.
The manually validated report/model files were preserved. Validation now accepts quoted or
unquoted TMDL measure identifiers and explicitly distinguishes schema compatibility checks.
The duplicate-reference rejection remains enforced on every saved visual query.

Exact 2.13 schema validation remains unavailable because Microsoft's schema URL returns 404.
The validator checks an in-memory copy against the pinned 2.12 schema (including all structural
constraints), reports the count separately, and never rewrites the saved report. Desktop success
is recorded from the user's manual validation, independently of schema compatibility coverage.


Final checkpoint checks executed after preserving Desktop serialization:

| Check | Result |
|---|---|
| Full default pytest | 99 passed, 6 skipped, 1 existing Starlette/httpx warning (27.95s) |
| Power BI tests with PostgreSQL | 5 passed (2.70s) |
| Schema/binding checks | 76 documents; 14 exact-schema and 62 explicitly reported compatibility checks; 62 visuals |
| Database preservation | 35 tables / 1,497 rows match the saved baseline hash |
| Ruff lint / format | Passed; 119 files formatted |
| git diff --check | Passed |
| Candidate credential/local-only scan | 138 source files reviewed; no secrets or local credential values found |

The scan's sole credential-pattern match was an unchanged Phase 6 README password placeholder,
verified as a placeholder. .env, PBIX, .pbi caches, backup folders and temporary artifacts remain
ignored and excluded. The checkpoint includes the saved PBIP/PBIR/TMDL, required theme/platform
metadata, source specifications, reproducible generator, validators, tests and evidence.

Staged whitespace review found Desktop-added blank lines at TMDL file ends. Only excess
terminal newlines were removed; model contents and lineage metadata were preserved.
