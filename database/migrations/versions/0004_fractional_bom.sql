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
           ROUND(o.planned_quantity * l.quantity * 1.0 / b.output_quantity, 6) AS gross_quantity,
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
