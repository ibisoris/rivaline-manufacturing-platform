CREATE VIEW vw_demand_history AS
SELECT h.dataset_code, h.product_id, p.code AS product_code, h.period_start,
       h.unit_of_measure, SUM(h.quantity) AS quantity, COUNT(*) AS source_rows
FROM demand_observations h JOIN products p ON p.id = h.product_id
GROUP BY h.dataset_code, h.product_id, p.code, h.period_start, h.unit_of_measure;

CREATE VIEW vw_forecast_accuracy AS
SELECT m.id, r.code AS run_code, r.dataset_code, r.training_cutoff,
       r.generated_at, r.algorithm_version, m.product_id, m.scope_key,
       m.unit_of_measure, m.model_name, m.evaluation_split, m.observations,
       m.mae, m.rmse, m.wape_pct
FROM forecast_metrics m JOIN forecast_runs r ON r.id = m.forecast_run_id;

CREATE VIEW vw_demand_forecast AS
SELECT d.id, d.product_id, p.code AS product_code, d.period_start, d.period_end,
       d.quantity, d.model_version, d.generated_at, r.code AS run_code,
       r.dataset_code, r.training_cutoff, r.horizon, m.model_name AS selected_model,
       m.unit_of_measure, m.mae AS validation_mae, m.rmse AS validation_rmse
FROM demand_forecasts d JOIN products p ON p.id = d.product_id
JOIN forecast_runs r ON d.source_system = 'phase5_forecast_v1'
AND d.source_record_id = r.code || ':' || CAST(d.product_id AS VARCHAR)
                        || ':' || CAST(d.period_start AS VARCHAR)
JOIN forecast_metrics m ON m.forecast_run_id = r.id AND m.product_id = d.product_id
AND m.evaluation_split = 'validation'
AND d.model_version = r.algorithm_version || ':' || m.model_name;

CREATE VIEW vw_forecast_backtest AS
SELECT b.id, r.code AS run_code, r.dataset_code, b.product_id, p.code AS product_code,
       b.unit_of_measure, b.model_name, b.evaluation_split, b.training_cutoff,
       b.period_start, b.actual_quantity, b.predicted_quantity,
       b.predicted_quantity - b.actual_quantity AS signed_error
FROM forecast_backtests b JOIN forecast_runs r ON r.id = b.forecast_run_id
JOIN products p ON p.id = b.product_id;
