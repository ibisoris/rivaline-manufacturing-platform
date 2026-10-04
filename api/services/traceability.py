"""Seven bulk queries for order lineage, independent of line/batch/inspection counts."""

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import operations as s
from database import models as m


def order_trace(session: Session, order_id: int) -> dict:
    header = session.execute(
        select(m.SalesOrder, m.Customer)
        .join(m.Customer, m.Customer.id == m.SalesOrder.customer_id)
        .where(m.SalesOrder.id == order_id)
    ).one_or_none()
    if header is None:
        raise HTTPException(404, "Sales order not found")
    order, customer = header
    lines = session.execute(
        select(m.SalesOrderLine, m.Product)
        .join(m.Product, m.Product.id == m.SalesOrderLine.product_id)
        .where(m.SalesOrderLine.sales_order_id == order_id)
        .order_by(m.SalesOrderLine.line_number)
    ).all()
    line_ids = [line.id for line, _ in lines]
    productions = list(
        session.scalars(
            select(m.ProductionOrder)
            .where(m.ProductionOrder.sales_order_line_id.in_(line_ids))
            .order_by(m.ProductionOrder.id)
        )
    )
    batches = list(
        session.scalars(
            select(m.ProductionBatch)
            .where(m.ProductionBatch.production_order_id.in_([p.id for p in productions]))
            .order_by(m.ProductionBatch.id)
        )
    )
    batch_ids = [b.id for b in batches]
    inspections = list(
        session.scalars(
            select(m.QualityInspection)
            .where(m.QualityInspection.production_batch_id.in_(batch_ids))
            .order_by(m.QualityInspection.id)
        )
    )
    consumption = session.execute(
        select(
            m.BatchMaterialConsumption,
            m.RawMaterial,
            m.PurchaseOrderLine,
            m.PurchaseOrder,
            m.Supplier,
        )
        .select_from(m.BatchMaterialConsumption)
        .join(m.RawMaterial, m.RawMaterial.id == m.BatchMaterialConsumption.raw_material_id)
        .join(
            m.PurchaseOrderLine,
            m.PurchaseOrderLine.id == m.BatchMaterialConsumption.purchase_order_line_id,
        )
        .join(m.PurchaseOrder, m.PurchaseOrder.id == m.PurchaseOrderLine.purchase_order_id)
        .join(m.Supplier, m.Supplier.id == m.PurchaseOrder.supplier_id)
        .where(m.BatchMaterialConsumption.production_batch_id.in_(batch_ids))
        .order_by(m.BatchMaterialConsumption.id)
    ).all()
    shipments = session.execute(
        select(m.ShipmentLine, m.Shipment)
        .join(m.Shipment, m.Shipment.id == m.ShipmentLine.shipment_id)
        .where(m.ShipmentLine.sales_order_line_id.in_(line_ids))
        .order_by(m.ShipmentLine.id)
    ).all()

    qc_by_batch, material_by_batch, batches_by_order = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    production_by_line, shipments_by_line = defaultdict(list), defaultdict(list)
    for quality in inspections:
        qc_by_batch[quality.production_batch_id].append(s.Quality.model_validate(quality))
    for used, material, purchase_line, purchase, supplier in consumption:
        material_by_batch[used.production_batch_id].append(
            {
                "id": used.id,
                "raw_material_id": material.id,
                "material_code": material.code,
                "unit_of_measure": material.unit_of_measure,
                "quantity": used.quantity,
                "supplier_lot_code": used.supplier_lot_code,
                "purchase_order_line_id": purchase_line.id,
                "purchase_order_id": purchase.id,
                "purchase_order_code": purchase.code,
                "supplier_id": supplier.id,
                "supplier_code": supplier.code,
                "source_system": used.source_system,
                "source_record_id": used.source_record_id,
            }
        )
    for batch in batches:
        batches_by_order[batch.production_order_id].append(
            {
                **s.Batch.model_validate(batch).model_dump(),
                "inspections": qc_by_batch[batch.id],
                "materials": material_by_batch[batch.id],
            }
        )
    for production in productions:
        production_by_line[production.sales_order_line_id].append(
            {
                **s.ProductionOrder.model_validate(production).model_dump(),
                "batches": batches_by_order[production.id],
            }
        )
    for line, shipment in shipments:
        shipments_by_line[line.sales_order_line_id].append(
            {
                **s.Shipment.model_validate(shipment).model_dump(),
                "shipment_line_id": line.id,
                "production_batch_id": line.production_batch_id,
                "quantity": line.quantity,
            }
        )
    return {
        **s.SalesOrder.model_validate(order).model_dump(),
        "customer": customer,
        "lines": [
            {
                **s.SalesLine.model_validate(line).model_dump(),
                "product": product,
                "production_orders": production_by_line[line.id],
                "shipments": shipments_by_line[line.id],
            }
            for line, product in lines
        ],
    }
