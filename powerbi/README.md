# Power BI consumption plan (later phase)

No dashboard or PBIX file is implemented. Phase 3 provides eight PostgreSQL reporting views;
see docs/19-api-and-analytics.md for grains and docs/20-kpi-dictionary.md for measures.

A future report should connect to PostgreSQL using an externally configured read-only reporting
role. Use integer keys for relationships and preserve view grain: sales line, production order,
inspection, purchase line and inventory lot. Pre-aggregated views avoid repeated header quantities.
Consume vw_operations_kpis/vw_operations_quantities for the same all-time definitions as the API.
Keep quantities separated by metric, item type and unit. Do not sum rates or issue counts across
joins that repeat rows. Define refresh cadence, date dimensions and any period-specific measures
before building reports. Authentication, role grants and credentials belong in secure local/host
configuration; no credentials are embedded in report assets.


Phase 4 adds vw_inventory_risk, vw_material_requirements and vw_reorder_recommendations.
Use the documented pooled-stock assumptions; do not sum historical recommendation runs together.
The run code identifies a calculation snapshot. See docs/22-inventory-and-reorder.md for grains
and limitations. No Power BI file or client connection has been implemented or validated.


Phase 5 adds vw_demand_history, vw_demand_forecast, vw_forecast_accuracy and vw_forecast_backtest.
Keep dataset, product, unit and forecast run/origin in joins. Backtests expose actual/predicted values;
metric rows separate validation from holdout and product from overall-unit scope. Do not sum
historical forecast vintages or add the archived evaluation universe to operational sales totals.
No Power BI artifact or client connection is included. See docs/24-demand-forecasting.md.
