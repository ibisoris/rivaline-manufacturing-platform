CREATE VIEW vw_material_requirements AS
WITH used AS (
    SELECT b.production_order_id, c.raw_material_id, SUM(c.quantity) AS consumed_quantity
    FROM batch_material_consumption c
    JOIN production_batches b ON b.id = c.production_batch_id
    GROUP BY b.production_order_id, c.raw_material_id
), gross AS (
    SELECT o.id AS production_order_id, o.code AS production_order_code,
           o.product_id, o.sales_order_line_id, o.bom_id, o.status AS production_status,
           o.planned_quantity, b.output_quantity, l.quantity AS bom_quantity,
           l.raw_material_id, r.code AS material_code, r.unit_of_measure,
           ROUND(o.planned_quantity * l.quantity / b.output_quantity, 6) AS gross_quantity,
           COALESCE(u.consumed_quantity, 0) AS consumed_quantity
    FROM production_orders o JOIN bills_of_material b ON b.id = o.bom_id
    JOIN bill_of_material_lines l ON l.bom_id = b.id
    JOIN raw_materials r ON r.id = l.raw_material_id
    LEFT JOIN used u ON u.production_order_id = o.id AND u.raw_material_id = l.raw_material_id
    WHERE o.status IN ('planned', 'released')
)
SELECT gross.*, CASE WHEN gross_quantity > consumed_quantity
       THEN gross_quantity - consumed_quantity ELSE 0 END AS required_quantity
FROM gross;

CREATE VIEW vw_inventory_risk AS
WITH stock AS (
    SELECT item_type, COALESCE(product_id, raw_material_id) AS item_id,
           SUM(on_hand_quantity) AS on_hand_quantity, SUM(reserved_quantity) AS reserved_quantity
    FROM vw_inventory_position GROUP BY item_type, COALESCE(product_id, raw_material_id)
), demand AS (
    SELECT 'raw_material' AS item_type, raw_material_id AS item_id,
           SUM(required_quantity) AS required_quantity FROM vw_material_requirements
    GROUP BY raw_material_id
    UNION ALL
    SELECT 'product', product_id, SUM(outstanding_quantity) FROM vw_order_fulfilment
    WHERE order_status = 'confirmed' GROUP BY product_id
), incoming AS (
    SELECT l.raw_material_id, SUM(l.quantity) AS incoming_quantity
    FROM purchase_order_lines l JOIN purchase_orders o ON o.id = l.purchase_order_id
    WHERE o.status = 'confirmed' GROUP BY l.raw_material_id
), items AS (
    SELECT 'raw_material' AS item_type, id AS item_id, code AS item_code, unit_of_measure
    FROM raw_materials
    UNION ALL SELECT 'product', id, code, unit_of_measure FROM products
), positions AS (
    SELECT i.*, COALESCE(s.on_hand_quantity, 0) AS on_hand_quantity,
           COALESCE(s.reserved_quantity, 0) AS reserved_quantity,
           COALESCE(d.required_quantity, 0) AS required_quantity,
           COALESCE(n.incoming_quantity, 0) AS incoming_quantity,
           COALESCE(s.on_hand_quantity, 0) - COALESCE(s.reserved_quantity, 0) AS available_quantity,
           p.id AS policy_id, p.warehouse_id AS destination_warehouse_id,
           p.unit_of_measure AS policy_unit, p.safety_stock, p.reorder_point,
           p.target_stock, p.minimum_order_quantity
    FROM items i LEFT JOIN stock s ON s.item_type = i.item_type AND s.item_id = i.item_id
    LEFT JOIN demand d ON d.item_type = i.item_type AND d.item_id = i.item_id
    LEFT JOIN incoming n ON i.item_type = 'raw_material' AND n.raw_material_id = i.item_id
    LEFT JOIN planning_policies p ON i.item_type = 'raw_material' AND p.raw_material_id = i.item_id
), projected AS (
    SELECT positions.*, available_quantity + incoming_quantity - required_quantity
           AS projected_quantity,
           (SELECT COUNT(*) FROM production_orders o
            WHERE o.status IN ('planned', 'released') AND NOT EXISTS
            (SELECT 1 FROM bill_of_material_lines l WHERE l.bom_id = o.bom_id))
           AS incomplete_bom_count FROM positions
)
SELECT projected.*,
       CASE WHEN projected_quantity < 0 THEN -projected_quantity ELSE 0 END AS shortage_quantity,
       CASE WHEN incomplete_bom_count > 0 OR policy_id IS NULL
                 OR policy_unit <> unit_of_measure THEN NULL
            WHEN projected_quantity < reorder_point THEN
                CASE WHEN target_stock - projected_quantity > minimum_order_quantity
                     THEN target_stock - projected_quantity ELSE minimum_order_quantity END
            ELSE 0 END AS recommended_quantity,
       CASE WHEN incomplete_bom_count > 0 THEN 'incomplete_bom'
            WHEN policy_id IS NULL THEN 'no_policy'
            WHEN policy_unit <> unit_of_measure THEN 'invalid_policy'
            WHEN projected_quantity < 0 THEN 'shortage'
            WHEN projected_quantity < safety_stock THEN 'below_safety'
            WHEN projected_quantity < reorder_point THEN 'below_reorder'
            WHEN projected_quantity = reorder_point THEN 'at_reorder'
            ELSE 'healthy' END AS risk_status
FROM projected;

CREATE VIEW vw_reorder_recommendations AS
SELECT r.id, r.raw_material_id, r.warehouse_id, r.quantity, r.reason, r.status,
       r.generated_at, p.code AS run_code, p.algorithm_version,
       r.source_system, r.source_record_id
FROM reorder_recommendations r LEFT JOIN planning_runs p
ON r.source_system = 'phase4_reorder_v1'
AND r.source_record_id = p.code || ':' || CAST(r.raw_material_id AS VARCHAR);
