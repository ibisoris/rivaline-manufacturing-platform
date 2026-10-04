"""Bound SELECT queries with deterministic ordering and fixed-count detail loading."""

from datetime import UTC, datetime, time

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import operations as s
from database import models as m


def filtered(statement, model, filters, date_column=None, timestamp=False):
    for name, value in filters.model_dump().items():
        if name in {"limit", "offset", "date_from", "date_to"} or value is None:
            continue
        if model is m.SalesOrder and name == "product_id":
            statement = statement.where(
                select(m.SalesOrderLine.id)
                .where(
                    m.SalesOrderLine.sales_order_id == m.SalesOrder.id,
                    m.SalesOrderLine.product_id == value,
                )
                .exists()
            )
        else:
            statement = statement.where(getattr(model, name) == value)
    if date_column is not None:
        if filters.date_from:
            start = (
                datetime.combine(filters.date_from, time.min, UTC)
                if timestamp
                else filters.date_from
            )
            statement = statement.where(date_column >= start)
        if filters.date_to:
            end = datetime.combine(filters.date_to, time.max, UTC) if timestamp else filters.date_to
            statement = statement.where(date_column <= end)
    return statement


def page(session: Session, statement, model, filters, mappings=False) -> dict:
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    result = session.execute(
        statement.order_by(model.id).limit(filters.limit).offset(filters.offset)
    )
    return {
        "items": list(result.mappings() if mappings else result.scalars()),
        "total": total,
        "limit": filters.limit,
        "offset": filters.offset,
    }


def inventory_query():
    return (
        select(
            m.Inventory.__table__,
            m.Warehouse.code.label("warehouse_code"),
            func.coalesce(m.Product.code, m.RawMaterial.code).label("item_code"),
            func.coalesce(m.Product.unit_of_measure, m.RawMaterial.unit_of_measure).label(
                "unit_of_measure"
            ),
            (m.Inventory.quantity - m.Inventory.reserved_quantity).label("available_quantity"),
        )
        .join(m.Warehouse, m.Warehouse.id == m.Inventory.warehouse_id)
        .outerjoin(m.Product, m.Product.id == m.Inventory.product_id)
        .outerjoin(m.RawMaterial, m.RawMaterial.id == m.Inventory.raw_material_id)
    )


def sales_detail(session: Session, order_id: int) -> dict:
    order = session.get(m.SalesOrder, order_id)
    if order is None:
        raise HTTPException(404, "Sales order not found")
    result = s.SalesOrder.model_validate(order).model_dump()
    result["lines"] = list(
        session.scalars(
            select(m.SalesOrderLine)
            .where(m.SalesOrderLine.sales_order_id == order_id)
            .order_by(m.SalesOrderLine.line_number)
        )
    )
    return result
