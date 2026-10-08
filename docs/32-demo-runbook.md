# Ten-minute technical demonstration runbook

This public runbook demonstrates the independent fictional Rivaline manufacturing platform.
All data is synthetic. The proposed 20% efficiency improvement is a business-case objective,
not a measured achievement. Use the existing prepared database; do not rebuild it during a demo.

## Preparation (before the ten-minute timer)

1. Open the repository in VS Code and a PowerShell terminal at its root. Python 3.12, the local
   virtual environment, dependencies and PostgreSQL must already be configured as in README.
2. Keep `.env` private. Start the existing PostgreSQL service using local administration tools
   if necessary. Docker users can use their existing Compose deployment; do not start a second
   database on an occupied port. Do not display credentials in the demonstration.
3. Run the read-only schema verifier. It should report 35 application tables and 1,497 rows for
   the preserved dataset. A differently rebuilt dataset can have different audit timestamps.
4. Start FastAPI in terminal A; leave it running. Stop this owned process with Ctrl+C afterward.
5. In terminal B, verify health and discover the actual order/product/run identifiers below.
6. Open `powerbi/RivalineOperations.pbip` in Desktop. Check Server/Database and selected run
   parameters, authenticate locally, refresh, then clear slicer selections. Do not regenerate
   the report or open the unrelated original PBIX expecting the current dashboard.
7. Prepare browser tabs for `http://127.0.0.1:8000/docs` and the README/screenshots. In VS Code,
   open the data-quality rules, ETL summary and final validation report. Rehearse transitions.

```powershell
# Terminal A: schema inspection is read-only; run_api starts a local server.
.\.venv\Scripts\python.exe -m scripts.verify_db
.\.venv\Scripts\python.exe -m scripts.run_api
```

```powershell
# Terminal B: parameter discovery, using the actual API responses.
$base = "http://127.0.0.1:8000"
Invoke-RestMethod "$base/health"
$orders = Invoke-RestMethod "$base/api/v1/sales-orders?limit=5"
$orderId = $orders.items[0].id
$products = Invoke-RestMethod "$base/api/v1/products"
$productId = ($products.items | Where-Object { $_.code -eq "SYN-FG-001" }).id
$forecastPage = Invoke-RestMethod "$base/api/v1/forecasts?limit=200"
$runCodes = @($forecastPage.items.run_code | Sort-Object -Unique)
if ($runCodes.Count -ne 1) { throw "Select the intended saved forecast run before continuing." }
$forecastRun = $runCodes[0]
```

Expected health JSON on the preserved dataset:

```json
{"application":"Rivaline Manufacturing Integrated Operations Platform","environment":"development","status":"ok","database":"up"}
```

Orders return `items`, `total: 48`, `limit: 5`, `offset: 0`. The first preserved order is SO-0001,
but use the returned ID. The forecast page contains 12 rows in one saved run. If several runs
exist, inspect the training cutoff and run code and use the same chosen vintage in Power BI.
Do not silently choose a different run to make numbers match a screenshot.

## Minutes 0-2: business problem and architecture

Show the README architecture diagram. Explain the problem of disconnected sales, stock,
purchasing, production, quality and dispatch records. Follow one path from source file to
validation, PostgreSQL, reporting view and Power BI. FastAPI is another consumer, not the
Power BI refresh transport. Separate the short operational history from the synthetic demand archive.

Show the proposed efficiency objective and its measurement boundary: quality-accepted kg per
scheduled labour-hour, controlled product mix/operating conditions, measured baseline and pilot.
No actual 20% improvement or financial ROI is claimed. The implemented outcome is explainable,
reproducible decision support on a synthetic dataset.

## Minutes 2-5: Power BI management pages

| View | Action | Expected preserved evidence |
|---|---|---|
| Executive Operations | Begin with cleared selections | 48 orders; 2 materials at risk; 100% batch QC; 8.535K kg forecast |
| Inventory & Procurement | Inspect reorder proposals and supplier/material orders | RM-002 1,000kg; RM-003 1,500kg; 2,500kg total; orders are not receipts |
| Demand & Forecasting | Compare history/forward forecast and holdout cards | Selected-policy MAE 18.416667kg, RMSE 23.973944kg |
| Production & Capacity | Inspect December and SYN-MIX; scroll relevant tables | 11.76h required, 10h available, 1.76h short; FG-002 844kg unmet |

Avoid interpreting the all-resource/all-month chart as the December mixing denominator.
The FG-002 line needs 8.44h; 11.76h is the shared resource total including FG-001.
Supplier filters affect procurement, not all inventory metrics. Forecast accuracy can become
blank under future-month filters; clear selections to restore the documented holdout context.
Tables are scrollable. The static screenshots preserve a viewport, not every row.

Briefly identify the remaining pages: Quality & Data Trust exposes QC and weighted ETL results;
Transformation & Value connects integration stages to management decisions. All six pages were
manually validated by the user in Phase 7. This runbook does not assert a new automated GUI test.

## Minutes 5-8: Swagger UI and operational evidence

At `/docs`, expand an endpoint, choose **Try it out**, enter parameters, then **Execute**.
Inspect the request URL, HTTP status and response body. The equivalent requests below are all
read-only. Keep terminal-B variables from preparation.

```powershell
Invoke-RestMethod "$base/api/v1/sales-orders?limit=5"
Invoke-RestMethod "$base/api/v1/traceability/order/$orderId" | ConvertTo-Json -Depth 12
Invoke-RestMethod "$base/api/v1/kpis/operations"
Invoke-RestMethod "$base/api/v1/reorder-recommendations?status=proposed"
Invoke-RestMethod "$base/api/v1/forecasts?limit=12"
Invoke-RestMethod "$base/api/v1/forecasts/evaluation?scope=overall&evaluation_split=test"
Invoke-RestMethod "$base/api/v1/planning/production-plan?forecast_run_code=$forecastRun&period_start=2026-12-01"
Invoke-RestMethod "$base/api/v1/planning/capacity?forecast_run_code=$forecastRun&period_start=2026-12-01"
```

| Response | What to verify |
|---|---|
| Traceability | Customer and product, nested production/batches, QC, material consumption, supplier/purchase and shipments |
| KPIs | `order_count=48`, `production_batch_count=48`, `data_quality_issue_count=96`; rates 89.66% / 10.34% |
| Recommendations | Two proposed rows with quantities serialized as Decimal strings |
| Forecast list | Saved run, cutoff 2026-09-30, three future months per product |
| Overall evaluation | Three candidate-model holdout rows; these are **not** the dashboard's mixed selected-policy aggregate |
| December plan | FG-002 `gross_demand="948.000000"`, `inventory_offset="104.000000"`, `net_requirement="844.000000"`, `status="CAPACITY_CONSTRAINED"` |
| Capacity | SYN-MIX required 11.76h / available 10h; overload 1.76h; utilisation 117.60% |

Optional computational scenario (substitute for another request to stay within the timer):

```powershell
$scenario = @{demands=@(@{product_id=$productId; period_start="2026-11-01"; quantity="5000"; unit_of_measure="kg"})} | ConvertTo-Json -Depth 3
Invoke-RestMethod -Method Post -Uri "$base/api/v1/planning/production-plan/what-if" -ContentType "application/json" -Body $scenario
```

POST expresses a structured calculation request here; it does not imply persistence. With the
preserved stock/policy, this alternative scenario has 3,000kg net requirement, 30h proposed,
10h available, 1,000kg allocated and 2,000kg unmet. It is not added to the saved forecast plan.

## Minutes 8-10: ETL and engineering evidence

Use VS Code's terminal and the validation report. These commands inspect existing evidence;
none reruns ingestion or saves plans.

```powershell
.\.venv\Scripts\python.exe -m scripts.run_etl summary
.\.venv\Scripts\python.exe -m scripts.run_etl reconcile
.\.venv\Scripts\python.exe -m scripts.run_etl trace --order SO-0001
.\.venv\Scripts\python.exe -m scripts.validate_powerbi
```

Expected latest ETL execution: `status=succeeded`, 464 extracted, 416 accepted and 48 rejected.
Reconciliation returns `ok=true`, `source_files_verified=true`, 944 target receipts and matching
source/target quantities. Accepted replay does not insert those 944 targets again. Across two
runs, 96 issue events refer to two inspections of the deliberately defective source rows.

Show [final test evidence](31-end-to-end-validation.md) rather than running the entire PostgreSQL
suite during the timer. Demonstrate the tests' purpose: valid relationships, no silent replay
changes, chronological evaluation, allocation constraints and report-binding consistency.

## Safety classification

| Commands | Effect |
|---|---|
| `verify_db`, ETL `summary/reconcile/trace/snapshot`, inventory `positions/requirements` | Database reads; reconciliation needs existing local quarantine summaries |
| GET routes and production what-if POST | Read-only request transactions; no persisted plan |
| `verify_phase9` | Read-only DB/API; isolated temporary fixture generation and temporary owned API process; writes local evidence JSON |
| `pytest --postgres` | Test writes in isolated schemas with outer rollback; requires CREATE privilege; run outside the timed demo |
| `migrate_db`, `seed_master_data`, ETL `run`, policy seeds, forecast/history ingest, `save-forecast` | Explicit preparation writes; never run to repair a demo without understanding the effect |
| `build_powerbi`, `generate_legacy`, `generate-history` | Overwrite owned local generated definitions/sources; not demo inspection commands |

## Troubleshooting and offline fallback

| Symptom | Check and response |
|---|---|
| Connection refused on port 8000 | Start terminal A; check API_HOST/API_PORT. Do not kill an unrelated process to free the port. |
| `/health` 503 | Check local PostgreSQL service and private POSTGRES_* settings. Health checks connectivity, not complete migrations. |
| Operational 503 with healthy server | Verify schema with `verify_db`; inspect local configuration. Avoid displaying raw credential-bearing exceptions. |
| 422 request | Read the structured `detail`; limit must be 1-200, IDs positive, run code 64 hex characters and plan period the first day of a month. |
| 404 trace/forecast | Discover IDs/run codes from the actual list responses. |
| 409 planning conflict | Check policy, BOM, units and unresolved confirmed demand assumptions. Do not manufacture missing data. |
| ETL reconciliation fails | Check original source hashes and matching summary/rejected exports. Do not rerun ETL merely to erase the symptom. |
| Power BI credentials prompt | Authenticate in Desktop; Python's .env is not its credential store. |
| Blank/wrong dashboard values | Clear slicers; check run parameters and database; refresh. Do not change DAX to force reference values. |
| Exact visual schema 2.13 URL unavailable | Automated report explicitly uses 2.12 structural compatibility checks; user Desktop validation is separate evidence. |
| Live services unavailable | Use the four README screenshots and saved validation JSON/report; clearly identify them as previously captured evidence. |

Afterward, stop only the API process started for this demonstration. Leave database contents,
Power BI definitions and source files unchanged. A fresh environment is prepared separately via
the README, not reconstructed during these ten minutes.
