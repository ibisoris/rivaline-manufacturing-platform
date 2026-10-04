# Demand forecasting and evaluation (Phase 5)

All history, business entities, formulas and evaluation results are synthetic portfolio examples.
Forecasting provides decision support only. No production orders, purchase orders, reorder proposals,
schedules or dashboards are created from forecasts. Phase 6 requires explicit approval.

## History assessment and target

The existing 48 sales orders cover only January-February 2026: 12 orders and two monthly observations
per product. That is insufficient for a meaningful seasonal/time-aware model comparison. The original
sales, shipment and planning data remains unchanged; its totals are not blended into the new series.

`etl/demand_history.py` extends the legacy export workflow with a separate, labelled archived-demand
CSV plus manifest. It is an alternative synthetic evaluation universe, not additional live orders.
This avoids changing previously verified operational KPIs, commitments or reorder calculations.
It also avoids claiming that generated archived demand is observed real customer behavior.

The target is booked finished-product demand quantity, aggregated at **product x calendar month**
in the product's canonical unit. The fixture has four products in kg, 24 months from October 2024
through September 2026, and two source fragments per product/month: 192 CSV rows aggregate to 96
monthly observations. These fragments are source records, not inferred customer transactions.

Generation uses local random seed 20261004. Monthly demand is:

```text
base + product_trend * month_index + calendar_month_effect + seeded_noise + explicit_spike
```

Product bases/trends are (600,+8), (850,+3), (450,0), (700,-4) kg/month. January-December effects
are [-30,-20,0,15,30,45,30,20,0,-10,-20,-35] kg. Integer noise is uniform from -40 to +40 using
the fixed seed. Product 2 adds 180 kg at zero-based month indices 7 and 18; product 1 adds 120 kg
at index 16. Each month's quantity is split 60%/40% into two exact Decimal source quantities.
Seasonality and spikes are explicitly teaching patterns, not evidence about actual coatings demand.

The manifest records dataset SYN-DEMAND-24M-V1, seed, source count, dates, product codes, synthetic
label and SHA-256. Generation rewrites only its own CSV/manifest, never the original six legacy
files. Default directory is configured by FORECAST_HISTORY_DIR in database/config.py; CLI --root
can override it. The new archive importer does not rerun the operational ETL.

## Ingestion, aggregation and missing periods

The importer checks headers, manifest checksum/identity, row count, product references, canonical
units, source-key duplicates, month-start dates, completed periods and finite non-negative Decimal
quantities with at most six decimal places. It requires the documented complete 24-month/four-product
coverage. Validation happens before inserting rows; an invalid batch is rejected atomically, with
no quantity imputation. This dedicated archive importer rejects the batch rather than using the
operational row-quarantine workflow. It retains source keys and file hashes in demand_observations.

Exact replay inserts zero. Conflicting source data or an unexpected persisted source key is rejected;
it is not silently updated. A corrected historical source requires an explicitly versioned archive
workflow. The supplied generator/importer deliberately supports this one fixed synthetic dataset;
a general archive version management UI is not implemented.

Monthly quantity is the sum of fragments with the same dataset/product/month/unit. Absence is not
zero: any missing monthly period causes evaluation to fail. An explicit recorded zero is valid.
Units must match the product; no kg/L conversion is inferred. Forecast history is distinct from
shipments, revenue, and unfulfilled orders. Calendar date semantics are separate from UTC run times.

## Models and arithmetic

Exactly three candidates are evaluated independently for every product:

| Model | Forecast rule |
|---|---|
| naive | Repeat the final training observation for every horizon month |
| moving_average | Repeat the mean of the last three training observations |
| linear_trend | Ordinary least squares of quantity on month index, extrapolated forward |

Naive is the mandatory baseline and participates in every comparison. Moving average and trend
have no tuned hyperparameters. There are no lag values from validation/test in a forecast origin's
training features. Models receive only the prefix available at that origin. Forecasts are floored
at zero and rounded to six decimals before evaluation and persistence.

The linear model uses the transparent closed-form covariance/variance slope and intercept.
All model, metric and operational quantity arithmetic uses Decimal (40-digit working precision
for regression/metrics). No heavy framework or new dependency was needed; scikit-learn is not
required for these three small exact-arithmetic rules. No claim of machine-learning superiority
is implied. No seasonal candidate is fitted from only two cycles of fabricated seasonal patterns.

## Chronological validation and leakage prevention

This version requires exactly 24 contiguous months and a three-month horizon. It does not randomly
split observations. Three non-overlapping validation blocks are produced by expanding windows:

| Stage | Training months | Cutoff | Predicted months |
|---|---:|---|---|
| Validation origin 1 | 1-12 | 2025-09-30 | Oct-Dec 2025 |
| Validation origin 2 | 1-15 | 2025-12-31 | Jan-Mar 2026 |
| Validation origin 3 | 1-18 | 2026-03-31 | Apr-Jun 2026 |
| Final holdout | 1-21 | 2026-06-30 | Jul-Sep 2026 |
| Forward refit | 1-24 | 2026-09-30 | Oct-Dec 2026 |

Each candidate has nine validation predictions and three final test predictions per product.
All candidates' holdout results are retained, but selection uses only validation metrics. The final
holdout is not used to choose the model or tune parameters. After evaluation, the selected model
is refitted on all 24 completed months for the forward forecast. Its training cutoff is explicitly
recorded; forward refitting is not represented as holdout evidence.

Database queries exclude observations after the requested cutoff before hashing/training. Cutoff
must be a completed month-end, and history must cover the required grid. Tests alter future/holdout
values and verify that earlier predictions and validation-based selection remain unchanged. Tests
also append a later database observation and verify that the earlier run replays identically.

## Metrics and selection

For non-negative actuals a and predictions p:

```text
MAE = sum(abs(a-p)) / n
RMSE = sqrt(sum((a-p)^2) / n)
WAPE percent = 100 * sum(abs(a-p)) / sum(a)
```

MAE/RMSE use the series quantity unit. WAPE is null when total actual demand is zero; zero periods
otherwise remain included. MAPE is not used. Metrics are rounded to six decimals and reported for
every model, both validation and test, per product and overall within each unit. Overall metrics
are calculated from pooled errors/actuals, not averages of product percentages; unlike units are
never pooled. The fixture produces 30 metric rows and 144 individual backtest predictions.

Select the lowest validation MAE separately for each product. Six-decimal ties favor naive, then
moving_average, then linear_trend. This deterministic simplicity rule can select the baseline.
Holdout metrics are disclosed even when another model performs better there. Do not retrospectively
change selection after inspecting holdout results. The measured results are in document 25.

## Uncertainty

Forecast responses expose the selected model's validation MAE and RMSE as historical error scales.
No lower/upper prediction intervals, confidence level or coverage guarantee is claimed. Nine
validation errors and three holdout errors per product on designed synthetic history do not justify
strong calibration claims. These error scales are not automatically stock buffers, safety stock,
worst-case bounds or forecasts of disruption. Structural breaks and unmodelled spikes can exceed them.

## Persistence and reproducibility

ForecastRun stores algorithm version forecast-v1, cutoff, horizon, full archived training inputs,
source hashes/keys, all model scores, every actual/predicted backtest pair and selected forecasts.
The run code is SHA-256 over canonical input JSON including the version and validation design.
Timestamp is not part of the hash. The existing unchanged demand_forecasts table holds 12 positive
or zero product-month predictions. model_version identifies algorithm and selected candidate;
source_system=phase5_forecast_v1 and source_record_id=run_hash:product_id:period_start connect each
row to its run using the existing unique source-key contract.

ForecastMetric and ForecastBacktest normalize the saved report for reliable SQL/BI consumption.
They deliberately repeat the immutable report's results, not recompute them from changing history.
Replay verifies saved quantities/metrics/backtest evidence and rejects missing/conflicting results;
it never silently repairs, duplicates or overwrites them. Changed relevant inputs/version/cutoff
produce another immutable run. Restoring old inputs returns that original run. A cutoff's future
observations are excluded and cannot create a new vintage for that earlier cutoff.

The explicit CLI owns a REPEATABLE READ transaction encompassing evaluation and persistence.
History import and forecast generation are separate explicit transactions. Single-process writers
are intended; database unique keys reject duplicate concurrent insertion, without a distributed
retry service. History/run immutability is an application policy, not protection from administrators
with direct SQL access. Run timestamps are aware UTC and API timestamps normalize to UTC.

## Read-only APIs

All GET routes are under /api/v1/forecasts. No HTTP route trains or persists a forecast.
Existing READ ONLY / REPEATABLE READ request handling, bounded pagination and Decimal strings apply.

| Route | Filters and behavior |
|---|---|
| /forecasts | product_id, run_code, model_version, date_from/date_to |
| /forecasts/{product_id} | Same filters, restricted to an existing integer product ID |
| /forecasts/evaluation | product_id, run_code, model_name, evaluation_split, scope=product/overall |
| /forecasts/history | product_id, dataset_code, date_from/date_to |

Date filters are inclusive against period_start. Lists use items/total/limit/offset, default 50,
maximum 200. Unknown products on the product route return 404; a known product with no matching
forecast returns an empty page. Invalid/unknown query parameters return 422; mutations return 405;
unavailable reporting tables return sanitized 503. Static evaluation/history paths precede the
product-ID path. OpenAPI version is 0.5.0, with all previous API contracts retained.

Forecast responses include product, period, quantity/unit, selected model/version, run/dataset,
generated time, training cutoff, horizon and uncertainty context. Listing without run_code includes
all historical vintages; do not add forecasts from different runs together. Current APIs serve
managed Phase 5 forecast rows; unrelated legacy rows without run evidence are not presented as
validated forecasts.

## Reporting views and migrations

| View | Grain |
|---|---|
| vw_demand_history | Dataset / product / month / unit; aggregated source quantity and fragment count |
| vw_demand_forecast | Persisted managed demand_forecast ID; selected model and validation error scale |
| vw_forecast_accuracy | Run / model / split / scope (product or overall-unit) |
| vw_forecast_backtest | Run / model / product / training cutoff / predicted period |

The backtest view includes actual_quantity, predicted_quantity and signed_error=predicted-actual.
It supports actual-versus-predicted BI displays without expanding JSON or mixing forecast origins.
Join history/forward forecasts by dataset/product/month/unit and keep run/vintage explicit. No
future actuals currently exist for Oct-Dec 2026; do not relabel forecasts as observed demand.
No Power BI dashboard or client connection is implemented.

Migration 0005_forecasting adds four tables and four views. Original 25 table contracts and 11 views
are unchanged. SQL is frozen in migration files, separate from evolving model definitions. Downgrade
refuses to remove populated archive/run evidence. Tests validate metadata equality, fixed earlier
revision contracts, upgrade/downgrade/reapply and prior-row preservation. PHASE4_TABLES freezes the
prior schema scope for comparisons; new forecast rows are separately identified as authorized additions.

## Forecast-to-material demonstration

The explicit demo-bom CLI takes a saved run and one product. It sums that product's three forecast
months and passes the quantity through the existing Phase 4 read-only active-BOM what-if function.
This yields component demand, baseline/scenario material positions and shortage, with no persistence.
It is an **incremental scenario**, not net firm demand, a schedule or a new reorder run. Existing
orders may overlap expected demand; combining them requires a separately approved netting policy.
The simple demo intentionally does not deduct finished-goods stock or allocate production capacity.
It uses the current active BOM and inventory position, which may differ from those at forecast time.

A zero total requires no additional BOM demand and is reported as a calculation conflict rather
than passing an invalid zero-quantity scenario. Missing/ambiguous active BOMs retain Phase 4 checks.
The run and forecast rows remain unchanged after the demonstration.

## Commands and limits

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate_db
.\.venv\Scripts\python.exe -m scripts.run_forecasting generate-history
.\.venv\Scripts\python.exe -m scripts.run_forecasting ingest-history
.\.venv\Scripts\python.exe -m scripts.run_forecasting forecast
.\.venv\Scripts\python.exe -m scripts.run_forecasting forecast
.\.venv\Scripts\python.exe -m scripts.run_forecasting demo-bom --run-code <returned-run-code> --product-id 1
.\.venv\Scripts\python.exe -m scripts.run_api
```

The default cutoff is 2026-09-30; --cutoff accepts an explicit completed month-end but still requires
24 complete months of the documented dataset. The fixed fixture is a bounded evaluation benchmark,
not a continuously updating production forecasting service. Synthetic patterns, small sample size,
no promotion/price/censoring features and no calibrated uncertainty limit generalization. No real
forecast improvement, financial benefit or stockout reduction is inferred. Production use would
require governed history revisions, measured demand semantics, drift monitoring, approved forecast
vintages, least-privilege roles and meaningful out-of-sample data. Local APIs remain unauthenticated.
