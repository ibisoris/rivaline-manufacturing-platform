# ADR 005: separate archived demand and immutable forecasting evidence

Status: accepted for the explicitly approved Phase 5 synthetic demonstration.

Existing sales has two monthly observations per product and cannot support meaningful time-aware
forecast evaluation. Add a deterministic, labelled 24-month archived-demand export and strict
importer. Keep it separate from operational sales: it is an alternative evaluation universe,
not extra current commitments or sales KPI activity. Preserve all prior operational evidence.

Use product/month quantities and three explainable Decimal models: naive, three-month mean and
closed-form linear trend. Select on expanding-window validation MAE, with a final untouched
three-month holdout; disclose every candidate's scores. Use historical error scales without
claiming calibrated prediction intervals. No extra forecasting dependency is justified.

Reuse demand_forecasts with its source-key uniqueness for forecast vintages. Four supporting tables
retain input history, immutable run reports, normalized metrics and actual/predicted backtest rows.
Reporting views make grains explicit. Writes are CLI-owned transactions; HTTP is read-only.
The forecast-to-BOM demonstration reuses the existing scenario function and never saves proposals.

See [the calculation and evaluation contract](../24-demand-forecasting.md) for exact assumptions,
formulas, replay semantics and limitations. No production scheduling or automatic order creation
is authorized in this phase.
