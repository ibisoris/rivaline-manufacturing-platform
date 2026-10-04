"""Atomic per-row insert-or-compare loading; changed trusted records are rejected."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from database import models as m
from etl.transform import Rejected, timestamp


def scalar(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def load(session, source: str, row: dict) -> tuple[list, int]:
    receipts = []
    inserted = 0
    system = "legacy_" + source
    record = row["record_id"]
    business = row["business_key"]

    def ensure(model, values, suffix="", natural=None):
        nonlocal inserted
        source_key = record + suffix
        existing = session.scalar(
            select(model).where(model.source_system == system, model.source_record_id == source_key)
        )
        if existing is None:
            if natural and session.scalar(select(model).filter_by(**natural)) is not None:
                raise Rejected(
                    "BUSINESS_KEY_CONFLICT", "Business key belongs to another source record"
                )
            existing = model(**values, source_system=system, source_record_id=source_key)
            session.add(existing)
            session.flush()
            inserted += 1
        elif any(scalar(getattr(existing, k)) != scalar(v) for k, v in values.items()):
            raise Rejected(
                "REPLAY_CONFLICT", "Previously accepted source record changed; review required"
            )
        receipts.append(
            {
                "table": model.__tablename__,
                "source_system": system,
                "source_record_id": source_key,
                "values": {k: scalar(v) for k, v in values.items()},
            }
        )
        return existing

    if source == "sales":
        header = ensure(
            m.SalesOrder,
            dict(
                code=business,
                customer_id=row["party"].id,
                order_date=row["order_date"],
                required_date=row["due_date"],
                status=row["status"],
            ),
            natural={"code": business},
        )
        ensure(
            m.SalesOrderLine,
            dict(
                sales_order_id=header.id,
                line_number=1,
                product_id=row["item"].id,
                quantity=row["quantity"],
                unit_price_gbp=row["unit_price"],
            ),
            "/1",
        )
    elif source == "purchasing":
        header = ensure(
            m.PurchaseOrder,
            dict(
                code=business,
                supplier_id=row["party"].id,
                order_date=row["order_date"],
                expected_date=row["due_date"],
                status=row["status"],
            ),
            natural={"code": business},
        )
        ensure(
            m.PurchaseOrderLine,
            dict(
                purchase_order_id=header.id,
                line_number=1,
                raw_material_id=row["item"].id,
                quantity=row["quantity"],
                unit_price_gbp=row["unit_price"],
            ),
            "/1",
        )
    elif source == "inventory":
        item_column = "raw_material_id" if isinstance(row["item"], m.RawMaterial) else "product_id"
        natural = {
            "warehouse_id": row["warehouse_ref"].id,
            item_column: row["item"].id,
            "lot_code": business,
        }
        ensure(
            m.Inventory,
            dict(**natural, quantity=row["quantity"], reserved_quantity=Decimal(0)),
            natural=natural,
        )
    elif source == "production":
        header = ensure(
            m.ProductionOrder,
            dict(
                code=business,
                product_id=row["item"].id,
                bom_id=row["bom_ref"].id,
                sales_order_line_id=row["line"].id,
                planned_quantity=row["quantity"],
                planned_start=row["start_date"],
                planned_end=row["end_date"],
                status="completed",
            ),
            natural={"code": business},
        )
        batch = ensure(
            m.ProductionBatch,
            dict(
                code=business,
                production_order_id=header.id,
                product_id=row["item"].id,
                actual_quantity=row["quantity"],
                status=row["status"],
            ),
            natural={"code": business},
        )
        for purchase, quantity, lot in row["consumption"]:
            ensure(
                m.BatchMaterialConsumption,
                dict(
                    production_batch_id=batch.id,
                    raw_material_id=purchase.raw_material_id,
                    purchase_order_line_id=purchase.id,
                    supplier_lot_code=lot,
                    quantity=quantity,
                ),
                "/" + str(purchase.raw_material_id),
            )
    elif source == "quality":
        natural = dict(production_batch_id=row["batch"].id, test_code=business)
        ensure(
            m.QualityInspection,
            dict(
                **natural,
                inspected_at=timestamp(row["inspection_date"]),
                measured_value=row["value"],
                unit_of_measure="score",
                result=row["status"],
            ),
            natural=natural,
        )
    else:
        header = ensure(
            m.Shipment,
            dict(
                code=business,
                warehouse_id=row["warehouse_ref"].id,
                shipped_at=timestamp(row["ship_date"]),
                status=row["status"],
                tracking_reference=business,
            ),
            natural={"code": business},
        )
        ensure(
            m.ShipmentLine,
            dict(
                shipment_id=header.id,
                sales_order_line_id=row["line"].id,
                production_batch_id=row["batch"].id,
                product_id=row["batch"].product_id,
                quantity=row["quantity"],
            ),
            "/1",
        )
    return receipts, inserted
