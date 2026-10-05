CREATE VIEW vw_production_plan AS
SELECT r.code AS plan_run_code, r.algorithm_version, r.generated_at,
       f.code AS forecast_run_code, l.*
FROM production_plan_lines l
JOIN production_plan_runs r ON r.id = l.plan_run_id
JOIN forecast_runs f ON f.id = r.forecast_run_id;

CREATE VIEW vw_capacity_utilisation AS
SELECT r.code AS plan_run_code, r.algorithm_version, r.generated_at,
       c.*, CASE WHEN c.overload_hours = 0 THEN 1 ELSE 0 END AS feasible
FROM production_capacity_results c JOIN production_plan_runs r ON r.id = c.plan_run_id;

CREATE VIEW vw_planning_constraints AS
SELECT * FROM vw_production_plan WHERE status <> 'FEASIBLE';

CREATE VIEW vw_forecast_to_production AS
SELECT plan_run_code, forecast_run_code, product_id, product_code, period_start,
       unit_of_measure, gross_demand AS forecast_quantity, inventory_offset, surplus_offset,
       net_requirement, proposed_quantity, allocated_quantity, unmet_quantity, batch_count,
       required_hours, available_hours, allocated_hours, overload_hours, utilisation_pct,
       status, explanation
FROM vw_production_plan;

CREATE VIEW vw_planning_materials AS
SELECT r.code AS plan_run_code, l.product_id, l.product_code, l.period_start, x.*
FROM production_material_results x
JOIN production_plan_lines l ON l.id = x.plan_line_id
JOIN production_plan_runs r ON r.id = l.plan_run_id;
