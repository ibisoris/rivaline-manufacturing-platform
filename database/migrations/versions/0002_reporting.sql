CREATE VIEW vw_inventory_position AS
SELECT i.id AS inventory_id, w.id AS warehouse_id, w.code AS warehouse_code,
       CASE WHEN i.product_id IS NOT NULL THEN 'product' ELSE 'raw_material' END AS item_type,
       i.product_id, i.raw_material_id, COALESCE(p.code, r.code) AS item_code,
       COALESCE(p.name, r.name) AS item_name,
       COALESCE(p.unit_of_measure, r.unit_of_measure) AS unit_of_measure,
       i.lot_code, i.quantity AS on_hand_quantity, i.reserved_quantity,
       i.quantity - i.reserved_quantity AS available_quantity,
       i.source_system, i.source_record_id
FROM inventory i JOIN warehouses w ON w.id = i.warehouse_id
LEFT JOIN products p ON p.id = i.product_id
LEFT JOIN raw_materials r ON r.id = i.raw_material_id;

CREATE VIEW vw_order_fulfilment AS
WITH dispatch AS (
    SELECT sl.sales_order_line_id, SUM(sl.quantity) AS shipped_quantity,
           MIN(s.shipped_at) AS first_shipped_at, MAX(s.shipped_at) AS last_shipped_at,
           COUNT(DISTINCT s.id) AS shipment_count
    FROM shipment_lines sl JOIN shipments s ON s.id = sl.shipment_id
    WHERE s.status IN ('dispatched', 'delivered')
    GROUP BY sl.sales_order_line_id
)
SELECT l.id AS sales_order_line_id, o.id AS sales_order_id, o.code AS order_code,
       c.id AS customer_id, c.code AS customer_code, p.id AS product_id, p.code AS product_code,
       p.unit_of_measure, o.order_date, o.required_date, o.status AS order_status,
       l.quantity AS ordered_quantity, COALESCE(d.shipped_quantity, 0) AS shipped_quantity,
       CASE WHEN l.quantity > COALESCE(d.shipped_quantity, 0)
            THEN l.quantity - COALESCE(d.shipped_quantity, 0) ELSE 0 END AS outstanding_quantity,
       CASE WHEN COALESCE(d.shipped_quantity, 0) > l.quantity
            THEN d.shipped_quantity - l.quantity ELSE 0 END AS over_shipped_quantity,
       COALESCE(d.shipment_count, 0) AS shipment_count, d.first_shipped_at, d.last_shipped_at
FROM sales_order_lines l JOIN sales_orders o ON o.id = l.sales_order_id
JOIN customers c ON c.id = o.customer_id JOIN products p ON p.id = l.product_id
LEFT JOIN dispatch d ON d.sales_order_line_id = l.id;

CREATE VIEW vw_production_performance AS
WITH qc AS (
    SELECT production_batch_id, COUNT(*) AS inspections,
           SUM(CASE WHEN result <> 'pass' THEN 1 ELSE 0 END) AS not_passed
    FROM quality_inspections GROUP BY production_batch_id
), batches AS (
    SELECT b.production_order_id, COUNT(*) AS batch_count,
           SUM(b.actual_quantity) AS actual_quantity,
           SUM(CASE WHEN q.inspections > 0 THEN 1 ELSE 0 END) AS inspected_batches,
           SUM(CASE WHEN q.inspections > 0 AND q.not_passed = 0 THEN 1 ELSE 0 END) AS passed_batches,
           SUM(CASE WHEN b.status = 'released' THEN 1 ELSE 0 END) AS released_batches
    FROM production_batches b LEFT JOIN qc q ON q.production_batch_id = b.id
    GROUP BY b.production_order_id
)
SELECT o.id AS production_order_id, o.code AS production_order_code,
       p.id AS product_id, p.code AS product_code, p.unit_of_measure,
       o.status AS order_status, o.planned_start, o.planned_end, o.planned_quantity,
       COALESCE(b.actual_quantity, 0) AS actual_quantity,
       COALESCE(b.batch_count, 0) AS batch_count,
       COALESCE(b.inspected_batches, 0) AS inspected_batches,
       COALESCE(b.passed_batches, 0) AS passed_batches,
       COALESCE(b.released_batches, 0) AS released_batches
FROM production_orders o JOIN products p ON p.id = o.product_id
LEFT JOIN batches b ON b.production_order_id = o.id;

CREATE VIEW vw_quality_performance AS
SELECT q.id AS inspection_id, b.id AS production_batch_id, b.code AS batch_code,
       b.status AS batch_status, p.id AS product_id, p.code AS product_code,
       q.test_code, q.inspected_at, q.measured_value, q.unit_of_measure AS measurement_unit,
       q.result, CASE WHEN q.result = 'pass' THEN 1 ELSE 0 END AS pass_indicator,
       CASE WHEN q.result = 'fail' THEN 1 ELSE 0 END AS fail_indicator,
       CASE WHEN q.result = 'pending' THEN 1 ELSE 0 END AS pending_indicator
FROM quality_inspections q JOIN production_batches b ON b.id = q.production_batch_id
JOIN products p ON p.id = b.product_id;

CREATE VIEW vw_supplier_material_flow AS
WITH consumption AS (
    SELECT purchase_order_line_id, SUM(quantity) AS consumed_quantity,
           COUNT(DISTINCT production_batch_id) AS consuming_batches
    FROM batch_material_consumption GROUP BY purchase_order_line_id
)
SELECT l.id AS purchase_order_line_id, o.id AS purchase_order_id, o.code AS purchase_order_code,
       s.id AS supplier_id, s.code AS supplier_code, r.id AS raw_material_id,
       r.code AS material_code, r.unit_of_measure, o.order_date, o.expected_date,
       o.status AS order_status, l.quantity AS ordered_quantity,
       CASE WHEN o.status = 'received' THEN 1 ELSE 0 END AS order_marked_received,
       COALESCE(c.consumed_quantity, 0) AS consumed_quantity,
       COALESCE(c.consuming_batches, 0) AS consuming_batches
FROM purchase_order_lines l JOIN purchase_orders o ON o.id = l.purchase_order_id
JOIN suppliers s ON s.id = o.supplier_id JOIN raw_materials r ON r.id = l.raw_material_id
LEFT JOIN consumption c ON c.purchase_order_line_id = l.id;

CREATE VIEW vw_data_quality_summary AS
SELECT r.id AS etl_run_id, r.code AS run_code, r.status AS run_status,
       r.started_at, r.finished_at, i.source_system, i.entity_name, i.rule_code, i.severity,
       COUNT(i.id) AS issue_count
FROM etl_runs r LEFT JOIN data_quality_issues i ON i.etl_run_id = r.id
GROUP BY r.id, r.code, r.status, r.started_at, r.finished_at,
         i.source_system, i.entity_name, i.rule_code, i.severity;

CREATE VIEW vw_operations_kpis AS
WITH production AS (
    SELECT COALESCE(SUM(batch_count), 0) AS batches,
           COALESCE(SUM(inspected_batches), 0) AS inspected,
           COALESCE(SUM(passed_batches), 0) AS passed
    FROM vw_production_performance WHERE order_status <> 'cancelled'
), etl AS (
    SELECT COUNT(*) AS successful_runs, COALESCE(SUM(rows_read), 0) AS extracted,
           COALESCE(SUM(rows_loaded), 0) AS accepted, COALESCE(SUM(rows_rejected), 0) AS rejected
    FROM etl_runs WHERE status = 'succeeded'
)
SELECT (SELECT COUNT(*) FROM sales_orders WHERE status <> 'cancelled') AS order_count,
       (SELECT COUNT(*) FROM shipments WHERE status IN ('dispatched', 'delivered')) AS shipment_count,
       p.batches AS production_batch_count, p.inspected AS inspected_batch_count,
       p.passed AS passed_batch_count,
       ROUND(100.0 * p.passed / NULLIF(p.inspected, 0), 6) AS batch_qc_pass_rate_pct,
       e.successful_runs AS etl_successful_runs, e.extracted AS etl_rows_extracted,
       e.accepted AS etl_rows_accepted, e.rejected AS etl_rows_rejected,
       ROUND(100.0 * e.accepted / NULLIF(e.extracted, 0), 6) AS etl_acceptance_rate_pct,
       ROUND(100.0 * e.rejected / NULLIF(e.extracted, 0), 6) AS etl_rejection_rate_pct,
       (SELECT COUNT(*) FROM etl_runs WHERE status = 'failed') AS etl_failed_runs,
       (SELECT COUNT(*) FROM data_quality_issues) AS data_quality_issue_count
FROM production p CROSS JOIN etl e;

CREATE VIEW vw_operations_quantities AS
SELECT 'sales_ordered' AS metric, 'product' AS item_type, unit_of_measure,
       SUM(ordered_quantity) AS quantity FROM vw_order_fulfilment
WHERE order_status <> 'cancelled' GROUP BY unit_of_measure
UNION ALL
SELECT 'sales_shipped', 'product', unit_of_measure, SUM(shipped_quantity)
FROM vw_order_fulfilment GROUP BY unit_of_measure
UNION ALL
SELECT 'inventory_on_hand', item_type, unit_of_measure, SUM(on_hand_quantity)
FROM vw_inventory_position GROUP BY item_type, unit_of_measure
UNION ALL
SELECT 'inventory_available', item_type, unit_of_measure, SUM(available_quantity)
FROM vw_inventory_position GROUP BY item_type, unit_of_measure
UNION ALL
SELECT 'production_planned', 'product', unit_of_measure, SUM(planned_quantity)
FROM vw_production_performance WHERE order_status <> 'cancelled' GROUP BY unit_of_measure
UNION ALL
SELECT 'production_actual', 'product', unit_of_measure, SUM(actual_quantity)
FROM vw_production_performance WHERE order_status <> 'cancelled' GROUP BY unit_of_measure
UNION ALL
SELECT 'procurement_ordered', 'raw_material', unit_of_measure, SUM(ordered_quantity)
FROM vw_supplier_material_flow WHERE order_status <> 'cancelled' GROUP BY unit_of_measure
UNION ALL
SELECT 'material_consumed', 'raw_material', unit_of_measure, SUM(consumed_quantity)
FROM vw_supplier_material_flow GROUP BY unit_of_measure;
