# Phase 5 validation and final report

Validated 2026-10-04 on native PostgreSQL 17.11 and Python 3.12.2. All business data and results
are synthetic. Phase 5 is complete; Phase 6 has not started.

Evidence: [pre-change fingerprint and history assessment](evidence/phase5-before.json),
[complete live results](evidence/phase5-live.json), [forecasting contract](24-demand-forecasting.md).

## VERIFIED

Deterministic archived demand, strict ingestion, product-month forecasting, three candidate models,
chronological validation/holdout, model selection, immutable forecast persistence, read-only APIs,
four reporting views and a non-persisting forecast-to-BOM demonstration are implemented and verified.
Native PostgreSQL is at 0005_forecasting. All previous business rows, operational trace/KPI outputs,
inventory positions and the existing reorder calculation run remain unchanged.

## HISTORICAL DATA

The original 48 sales orders provide only January-February 2026: two monthly observations and
12 orders per product. No meaningful forecast evaluation was claimed from that short history.
The separate SYN-DEMAND-24M-V1 archived-demand fixture has 192 source rows, aggregating to 96
product-month observations across four products, October 2024-September 2026, all kg.

Fixed seed 20261004 generates documented base/trend, mild monthly effects, integer noise and
occasional explicit spikes. A manifest records provenance and source checksum:
`0ecfe4e1be18c40e82fdc390393ef3d841532cd44caecfa1e2ef246b30ce7cf0`.
Generation was repeated byte-deterministically. First ingestion inserted 192 records; replay
inserted zero. Missing periods, bad units/dates/quantities, duplicates and conflicting replay are
rejected rather than silently filled or overwritten. The existing operational sales exports,
orders and KPI totals were not extended or replaced.

## FORECASTING GRAIN

Target: archived booked finished-product demand quantity. Grain: product x calendar month in
canonical units. History: exactly 24 complete months; cutoff 2026-09-30; horizon three months,
October-December 2026. Two source fragments are summed per product/month. Missing is not zero;
explicit zero-demand observations are valid. Forecast vintages retain their run IDs.

## MODELS EVALUATED

Naive repeats the last observation; moving_average repeats the last-three-month mean; linear_trend
uses exact-arithmetic ordinary least squares against month index. Predictions are non-negative and
rounded to six decimal places. Decimal arithmetic avoids introducing binary floats for quantities.
No deep learning, heavy forecasting library, tuned hyperparameter search or new dependency was added.

## VALIDATION DESIGN

Expanding training prefixes of 12, 15 and 18 months each predict the next three months, producing
nine non-overlapping validation observations per product/model. The final three months are held out:
training through June 2026 predicts July-September 2026. Selection uses validation MAE only, with
ties favoring naive, then moving_average, then linear_trend. All candidates' holdout scores are
retained without changing selection. Selected models refit all 24 months for the forward forecast.

Tests alter holdout values and verify unchanged validation selection and earlier predictions.
Appending an observation after cutoff does not change or duplicate the earlier forecast run.
No random train/test split, target leakage or future-period imputation is used.

## MODEL PERFORMANCE

Measured synthetic results; MAE/RMSE in kg, WAPE in percent. Overall scores pool individual errors
within kg and do not average product percentages. Every candidate is included.

| Split | Candidate | Observations | MAE kg | RMSE kg | WAPE % |
|---|---|---:|---:|---:|---:|
| validation | naive | 36 | 38.388889 | 52.455802 | 5.601492 |
| validation | moving_average | 36 | 40.500000 | 59.507703 | 5.909533 |
| validation | linear_trend | 36 | 46.705403 | 61.991344 | 6.814991 |
| test | naive | 12 | 21.166667 | 22.996377 | 2.970065 |
| test | moving_average | 12 | 32.444445 | 42.172925 | 4.552541 |
| test | linear_trend | 12 | 30.068182 | 35.475307 | 4.219109 |

Full product-level results:

| Product | Candidate | Validation MAE | Validation RMSE | Validation WAPE % | Holdout MAE | Holdout RMSE | Holdout WAPE % |
|---|---|---:|---:|---:|---:|---:|---:|
| SYN-FG-001 | naive | 60.666667 | 72.714052 | 8.313033 | 20.666667 | 20.928450 | 2.658662 |
| SYN-FG-001 | moving_average | 47.962963 | 61.246618 | 6.572270 | 4.333333 | 4.932883 | 0.557461 |
| SYN-FG-001 | linear_trend | 55.177117 | 65.352215 | 7.560811 | 26.924675 | 29.223683 | 3.463723 |
| SYN-FG-002 | naive | 41.888889 | 63.582842 | 4.569143 | 11.333333 | 12.727922 | 1.214286 |
| SYN-FG-002 | moving_average | 70.037037 | 94.147048 | 7.639478 | 70.333334 | 71.323208 | 7.535714 |
| SYN-FG-002 | linear_trend | 80.637935 | 95.965163 | 8.795800 | 35.728138 | 36.362395 | 3.828015 |
| SYN-FG-003 | naive | 20.666667 | 22.370616 | 4.480848 | 20.666667 | 21.924112 | 4.249486 |
| SYN-FG-003 | moving_average | 25.148148 | 30.440592 | 5.452501 | 17.777778 | 19.258476 | 3.655472 |
| SYN-FG-003 | linear_trend | 26.932828 | 33.204834 | 5.839447 | 17.125541 | 21.814072 | 3.521359 |
| SYN-FG-004 | naive | 30.333333 | 34.291236 | 4.787794 | 32.000000 | 32.166235 | 4.895461 |
| SYN-FG-004 | moving_average | 18.851852 | 24.964419 | 2.975564 | 37.333333 | 40.398020 | 5.711372 |
| SYN-FG-004 | linear_trend | 24.073733 | 28.087747 | 3.799782 | 40.494373 | 48.804593 | 6.194958 |

Naive is best when one candidate is applied uniformly across all four products. The actual selected
per-product policy has validation MAE 32.342593, RMSE 47.216503 and WAPE 4.719250%; its holdout
MAE is 18.416667, RMSE 23.973944 and WAPE 2.584191%. Relative to uniform naive, selected-policy
holdout MAE/WAPE are lower but RMSE is higher (23.973944 versus 22.996377). This is a tradeoff on a
small synthetic holdout, not proof of broad model superiority or a real business improvement.
No stockout-reduction or financial-benefit claim is made.

## SELECTED MODEL

Validation-based selection is product-specific: moving_average for SYN-FG-001 and SYN-FG-004;
naive for SYN-FG-002 and SYN-FG-003. Linear trend was not selected. The baseline is retained when
it wins. Selection was not revised after viewing final holdout results.

## FORWARD FORECAST RESULTS

| Product | Selected model | October kg | November kg | December kg |
|---|---|---:|---:|---:|
| SYN-FG-001 | moving_average | 777.333333 | 777.333333 | 777.333333 |
| SYN-FG-002 | naive | 948.000000 | 948.000000 | 948.000000 |
| SYN-FG-003 | naive | 466.000000 | 466.000000 | 466.000000 |
| SYN-FG-004 | moving_average | 653.666667 | 653.666667 | 653.666667 |

Exactly 12 demand_forecasts rows were saved under one run:
`1e8d547d27460bb77d408e542c17682cd11ea6b745bd4dd898ec6d34b135464e`.
Generated at `2026-10-04T21:20:24.265090+00:00`; algorithm version forecast-v1. Replay returned created=false,
identical forecast quantities, metrics and generated timestamp; no new forecast run or rows were
created. Changed-input tests preserve the original run and add a separate version; conflicting
saved evidence is rejected rather than silently repaired.

## UNCERTAINTY APPROACH

Responses expose the selected model's historical validation MAE and RMSE as error scales. No
prediction intervals or confidence/coverage guarantees are presented. Nine validation errors and
three holdout errors per product on designed synthetic data are too limited for strong calibration
claims. Error scales must not be interpreted as guaranteed stock buffers or worst-case limits.

## FORECAST-TO-BOM DEMONSTRATION

The saved SYN-FG-001 three-month forecast totals 2,331.999999 kg after six-decimal rounding.
Its existing synthetic BOM has four 25 kg component lines per 100 kg output. The read-only demo
therefore calculates 583.000000 kg requirement for each material, compares with 2,000 kg available,
and reports 1,417 kg remaining projected stock and zero physical shortage per component.

The Phase 4 scenario also displays policy-based hypothetical quantities, but persists none of them.
This is an incremental scenario, not demand netting, a schedule, a procurement action or a claim
that every forecasted unit must be produced. Existing firm demand may overlap forecasts. No
production order, purchase order, stock movement or saved reorder proposal was changed.

## API ENDPOINTS

Four GET routes were added under /api/v1:

- /forecasts: saved forecasts, filtered by product, run, model version and period.
- /forecasts/{product_id}: forecasts for one known integer product ID.
- /forecasts/evaluation: all candidate validation/test metrics with product/overall scope filters.
- /forecasts/history: archived product-month demand with product/dataset/date filters.

Pydantic schemas, bounded pagination, UTC generated timestamps and Decimal strings are documented
in OpenAPI version 0.5.0. HTTP remains READ ONLY / REPEATABLE READ; it never trains or persists.
Live checks on 127.0.0.1:18085 returned 200 for health/docs/OpenAPI, all four routes, run/product/date
filters and existing Phase 3/4 routes. Unknown product returned 404; limit=201 returned 422.
Automated tests verify additional 422 cases and 405 for mutation. The temporary API process stopped.
OpenAPI has 27 paths including health. All live requests are recorded in the evidence JSON.

## REPORTING VIEWS

| View | Grain | Verified rows |
|---|---|---:|
| vw_demand_history | Dataset/product/month/unit | 96 |
| vw_demand_forecast | Persisted managed forecast ID | 12 |
| vw_forecast_accuracy | Run/model/split/product or overall-unit scope | 30 |
| vw_forecast_backtest | Run/model/product/training cutoff/predicted period | 144 |

Backtests expose actual, predicted and signed error directly for later BI consumption. Dataset,
unit, run and origin must remain explicit; historical vintages and operational sales must not be
summed together. No dashboard file or Power BI connection has been implemented.

## MIGRATIONS

0005_forecasting adds demand_observations, forecast_runs, forecast_metrics and forecast_backtests,
plus four reporting views. The existing demand_forecasts contract is reused unchanged. All original
25 table contracts and 11 views remain. Live schema verification matched all 29 current tables;
PostgreSQL tests also compare migration output to current SQLAlchemy metadata and exercise
upgrade/downgrade/reapplication. Downgrade refuses to remove populated archive/run evidence.
Earlier-phase migration tests target their original fixed revisions.

## TEST RESULTS

| Check | Final executed result |
|---|---|
| Default pytest | 78 passed, 4 skipped, 1 warning; 19.83 s |
| PostgreSQL-enabled pytest | 126 passed, 1 warning; 66.87 s |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| pip check | No broken requirements found |
| Native schema/master verification | Passed; all 29 tables; zero remaining temporary schemas |
| Live generation, replay and HTTP | Passed |
| .env Git checks | Ignored and untracked |

Default skips are PostgreSQL migration checks; default tests do not require PostgreSQL. The live
suite includes real PostgreSQL variants in rollback-isolated schemas as well as SQLite portability
evidence. The existing upstream Starlette/httpx TestClient deprecation warning remains.

Coverage includes deterministic fixtures, aggregation, missing-period rejection, chronology and
leakage, all three models, MAE/RMSE/WAPE including zero denominators, deterministic selection,
non-negative predictions, replay/conflicts/history, API filters, reporting grains, BOM calculations,
migrations and preservation of earlier behavior.

## DATA PRESERVATION

Pre-migration and final fingerprints over all 1,085 original Phase 1-4 rows match exactly:
`b81d0d0b958ecff3173ba80a4099063055b8901589559e206cf8d9807928913b`.
This includes the original sales/production/stock, master/BOM data, two ETL runs, 96 DQ issues,
four planning policies, one planning run and two saved reorder proposals.

Authorized additions: 192 archived demand observations, one forecast run, 30 metrics, 144 backtest
rows and 12 forecast rows: 379 additions, 1,464 total rows. The preservation snapshot excludes only
these new tables and explicitly identified new forecast rows; existing values/timestamps remain
covered. Independent full-database verifier fingerprint after additions:
`2fe0aa4066f70a7e668eeb7733a389894332bcf2245300f0fd2081fe9bdc6f00`.

Phase 3 trace and KPI JSON match saved Phase 3 evidence exactly. Phase 4 inventory-position JSON
matches its saved evidence. Re-running the Phase 4 calculation returns its original run with no
new proposals. No operational ETL reload or original legacy-file rewrite occurred.

## FILES CHANGED

The repository remains untracked with no committed baseline; this is the Phase 5 change inventory:

- database/models.py and database/config.py.
- database/migrations/versions/0005_forecasting.py, 0005_tables.sql, 0005_forecasting.sql.
- etl/demand_history.py; data/legacy/forecast_history/demand_history.csv and manifest.json.
- planning/forecast_models.py and planning/forecasting.py.
- api/main.py, api/routers/forecasting.py, api/schemas/forecasting.py.
- scripts/run_forecasting.py and scripts/verify_phase5.py.
- tests/test_forecasting.py; fixed revision/current-schema/OpenAPI expectations in
  tests/test_foundation.py, tests/test_api_analytics.py and tests/test_planning.py.
- README.md, powerbi/README.md, docs 06/10/14/20/24/25, ADR 005,
  docs/evidence/phase5-before.json and docs/evidence/phase5-live.json.

No dependencies, secrets, commits, pushes or Phase 6 implementation were added.

## ISSUES/FIXES

Existing history was insufficient; resolved with a clearly separated, versioned synthetic archive,
not invented conclusions from two monthly points. Forecast-history date parameters were explicitly
typed to avoid SQLite's deprecated date adapter; final runs retain only the existing TestClient warning.

Adding the backtest view accidentally changed a test expectation from 144 to 154 through an overly
broad text replacement. Corrected that assertion and added explicit persisted/backtest-view count
checks; both full suites subsequently passed. Ruff formatting findings were resolved.
The Windows sandbox helper failed to start, requiring execution escalation; no global Git settings
or database roles were changed. Earlier behavior assertions were retained as schema/path inventories
were extended and migration tests pinned to their own historical revisions.

## LIMITATIONS

Results describe one designed synthetic 24-month dataset and three simple models. There are only
three final holdout periods per product. Models have no promotion, price, stockout censoring or
external drivers; no calibrated intervals or production performance guarantee is claimed. The
fixture is not a general live archive-management service. Forecasts are separate from firm demand;
no automatic netting, capacity planning, scheduling, orders or purchasing is implemented.

Local APIs have no authentication; writers are intended for single-process CLI use. Database
uniqueness rejects concurrent duplicates but no concurrency/load certification was attempted.
Docker remains unverified because virtualization is disabled. No real customer/manufacturer data,
cloud deployment, Power BI client connection or dashboard is involved.

## EXACT COMMANDS RUN

From the repository root with the existing virtual environment:

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_forecasting.py --tb=short
.venv\Scripts\python.exe -m pytest -q tests/test_forecasting.py --postgres --tb=short
.venv\Scripts\python.exe -m pytest -q --tb=short
.venv\Scripts\python.exe -m pytest -q --postgres --tb=short
.venv\Scripts\python.exe -m ruff check . --fix
.venv\Scripts\python.exe -m ruff format .
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m scripts.verify_phase5
.venv\Scripts\python.exe -m scripts.verify_db
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform check-ignore .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform ls-files -- .env
git -c safe.directory=D:/GITHUB_JOB_PROJECTS/rivaline-manufacturing-platform status --short
```

verify_phase5 invokes scripts.migrate_db, then scripts.run_forecasting generate-history twice,
ingest-history twice, forecast twice and demo-bom with the saved run code/product 1. It starts
scripts.run_api with process-only API_HOST=127.0.0.1 and API_PORT=18085, exercises recorded routes,
and stops the process. Its source retains the precise assertions. These are the same entry points
as the README demo. Inline Python captured the pre-change snapshot/history assessment and summarized
the selected-policy metrics. No password was printed or placed in tracked files.

## RECOMMENDED PHASE 6

Seek explicit approval for production-planning scope. First agree how forecasts and firm orders
are netted, how finished stock, material allocations/receipts and capacity constrain decisions,
and how scenarios remain separate from approved orders. Do not infer scheduling or automatic
procurement authorization from this forecasting phase. Phase 6 has not begun.
