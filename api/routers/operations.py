"""Versioned read-only operational resources."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from analytics.queries import operations_kpis
from api.dependencies import read_session
from api.schemas import filters as f
from api.schemas import operations as s
from api.services.operations import filtered, inventory_query, page, sales_detail
from api.services.traceability import order_trace
from database import models as m

router = APIRouter(
    prefix="/api/v1",
    tags=["Operations"],
    responses={503: {"description": "Operational database unavailable"}},
)
ReadSession = Annotated[Session, Depends(read_session)]
ResourceId = Annotated[
    int, Path(ge=1, description="Existing integer database resource ID", examples=[1])
]


@router.get(
    "/products",
    response_model=s.Page[s.Product],
    summary="List products",
    description="Read trusted records ordered by integer ID. Decimal values are JSON strings.",
)
def list_products(session: ReadSession, filters: Annotated[f.MasterFilter, Query()]):
    statement = filtered(select(m.Product), m.Product, filters, None, timestamp=False)
    return page(session, statement, m.Product, filters)


@router.get(
    "/raw-materials",
    response_model=s.Page[s.RawMaterial],
    summary="List raw materials",
    description="Read trusted records ordered by integer ID. Decimal values are JSON strings.",
)
def list_raw_materials(session: ReadSession, filters: Annotated[f.MasterFilter, Query()]):
    statement = filtered(select(m.RawMaterial), m.RawMaterial, filters, None, timestamp=False)
    return page(session, statement, m.RawMaterial, filters)


@router.get(
    "/suppliers",
    response_model=s.Page[s.Master],
    summary="List suppliers",
    description="Read trusted records ordered by integer ID. Decimal values are JSON strings.",
)
def list_suppliers(session: ReadSession, filters: Annotated[f.MasterFilter, Query()]):
    statement = filtered(select(m.Supplier), m.Supplier, filters, None, timestamp=False)
    return page(session, statement, m.Supplier, filters)


@router.get(
    "/customers",
    response_model=s.Page[s.Master],
    summary="List customers",
    description="Read trusted records ordered by integer ID. Decimal values are JSON strings.",
)
def list_customers(session: ReadSession, filters: Annotated[f.MasterFilter, Query()]):
    statement = filtered(select(m.Customer), m.Customer, filters, None, timestamp=False)
    return page(session, statement, m.Customer, filters)


@router.get(
    "/sales-orders",
    response_model=s.Page[s.SalesOrder],
    summary="List sales orders",
    description=(
        "Read trusted records ordered by integer ID. Decimal values are JSON strings. "
        "Date filters apply inclusively to order_date."
    ),
)
def list_sales_orders(session: ReadSession, filters: Annotated[f.SalesFilter, Query()]):
    statement = filtered(
        select(m.SalesOrder), m.SalesOrder, filters, m.SalesOrder.order_date, timestamp=False
    )
    return page(session, statement, m.SalesOrder, filters)


@router.get(
    "/purchase-orders",
    response_model=s.Page[s.PurchaseOrder],
    summary="List purchase orders",
    description=(
        "Read trusted records ordered by integer ID. Decimal values are JSON strings. "
        "Date filters apply inclusively to order_date."
    ),
)
def list_purchase_orders(session: ReadSession, filters: Annotated[f.PurchaseFilter, Query()]):
    statement = filtered(
        select(m.PurchaseOrder),
        m.PurchaseOrder,
        filters,
        m.PurchaseOrder.order_date,
        timestamp=False,
    )
    return page(session, statement, m.PurchaseOrder, filters)


@router.get(
    "/production-orders",
    response_model=s.Page[s.ProductionOrder],
    summary="List production orders",
    description=(
        "Read trusted records ordered by integer ID. Decimal values are JSON strings. "
        "Date filters apply inclusively to planned_start."
    ),
)
def list_production_orders(session: ReadSession, filters: Annotated[f.ProductionFilter, Query()]):
    statement = filtered(
        select(m.ProductionOrder),
        m.ProductionOrder,
        filters,
        m.ProductionOrder.planned_start,
        timestamp=False,
    )
    return page(session, statement, m.ProductionOrder, filters)


@router.get(
    "/production-batches",
    response_model=s.Page[s.Batch],
    summary="List production batches",
    description="Read trusted records ordered by integer ID. Decimal values are JSON strings.",
)
def list_production_batches(session: ReadSession, filters: Annotated[f.BatchFilter, Query()]):
    statement = filtered(
        select(m.ProductionBatch), m.ProductionBatch, filters, None, timestamp=False
    )
    return page(session, statement, m.ProductionBatch, filters)


@router.get(
    "/quality-inspections",
    response_model=s.Page[s.Quality],
    summary="List quality inspections",
    description=(
        "Read trusted records ordered by integer ID. Decimal values are JSON strings. "
        "Date filters apply inclusively to inspected_at in UTC."
    ),
)
def list_quality_inspections(session: ReadSession, filters: Annotated[f.QualityFilter, Query()]):
    statement = filtered(
        select(m.QualityInspection),
        m.QualityInspection,
        filters,
        m.QualityInspection.inspected_at,
        timestamp=True,
    )
    return page(session, statement, m.QualityInspection, filters)


@router.get(
    "/shipments",
    response_model=s.Page[s.Shipment],
    summary="List shipments",
    description=(
        "Read trusted records ordered by integer ID. Decimal values are JSON strings. "
        "Date filters apply inclusively to shipped_at in UTC."
    ),
)
def list_shipments(session: ReadSession, filters: Annotated[f.ShipmentFilter, Query()]):
    statement = filtered(
        select(m.Shipment), m.Shipment, filters, m.Shipment.shipped_at, timestamp=True
    )
    return page(session, statement, m.Shipment, filters)


@router.get(
    "/etl-runs",
    response_model=s.Page[s.EtlRun],
    summary="List etl runs",
    description=(
        "Read trusted records ordered by integer ID. Decimal values are JSON strings. "
        "Date filters apply inclusively to started_at in UTC."
    ),
)
def list_etl_runs(session: ReadSession, filters: Annotated[f.EtlFilter, Query()]):
    statement = filtered(select(m.EtlRun), m.EtlRun, filters, m.EtlRun.started_at, timestamp=True)
    return page(session, statement, m.EtlRun, filters)


@router.get(
    "/data-quality-issues",
    response_model=s.Page[s.DataQualityIssue],
    summary="List data quality issues",
    description=(
        "Read trusted records ordered by integer ID. Decimal values are JSON strings. "
        "Date filters apply inclusively to created_at in UTC. Raw quarantine payloads are "
        "intentionally omitted."
    ),
)
def list_data_quality_issues(session: ReadSession, filters: Annotated[f.IssueFilter, Query()]):
    statement = filtered(
        select(m.DataQualityIssue),
        m.DataQualityIssue,
        filters,
        m.DataQualityIssue.created_at,
        timestamp=True,
    )
    return page(session, statement, m.DataQualityIssue, filters)


@router.get(
    "/inventory",
    response_model=s.Page[s.Inventory],
    summary="List item/warehouse/lot stock",
    description="Snapshot quantities in each item's canonical unit; not a live stock ledger.",
)
def inventory(session: ReadSession, filters: Annotated[f.InventoryFilter, Query()]):
    statement = filtered(inventory_query(), m.Inventory, filters)
    return page(session, statement, m.Inventory, filters, mappings=True)


@router.get(
    "/inventory/{inventory_id}",
    response_model=s.Inventory,
    summary="Read one inventory position",
    responses={404: {"description": "Unknown inventory ID"}},
)
def inventory_detail(inventory_id: ResourceId, session: ReadSession):
    row = (
        session.execute(inventory_query().where(m.Inventory.id == inventory_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Inventory position not found")
    return row


@router.get(
    "/sales-orders/{order_id}",
    response_model=s.SalesDetail,
    summary="Read a sales order and its lines",
    responses={404: {"description": "Unknown order ID"}},
)
def order_detail(order_id: ResourceId, session: ReadSession):
    return sales_detail(session, order_id)


@router.get(
    "/traceability/order/{order_id}",
    response_model=s.OrderTrace,
    tags=["Traceability"],
    summary="Trace an order through production, quality, suppliers and shipments",
    description="Real foreign-key lineage. Missing downstream stages are empty arrays. "
    "Seven bulk SELECTs avoid per-line or per-batch queries.",
    responses={404: {"description": "Unknown order ID"}},
)
def traceability(order_id: ResourceId, session: ReadSession):
    return order_trace(session, order_id)


@router.get(
    "/kpis/operations",
    response_model=s.OperationsKpis,
    tags=["Analytics"],
    summary="Read all-time operational KPIs",
    description="Uses reporting views shared with future BI consumers. Quantities are grouped "
    "by metric, item type and unit. Rates are percentages; undefined rates are null. "
    "Successful ETL execution counters include replay, not unique business rows.",
)
def kpis(session: ReadSession):
    return operations_kpis(session)
