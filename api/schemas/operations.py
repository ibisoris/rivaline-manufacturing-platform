"""Version 1 read contracts. Decimal quantities serialize as JSON strings."""

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Master(ReadModel):
    id: int
    code: str
    name: str
    active: bool


class Product(Master):
    unit_of_measure: str


class RawMaterial(Product):
    category: str
    preferred_supplier_id: int | None


class Inventory(ReadModel):
    id: int
    warehouse_id: int
    warehouse_code: str
    product_id: int | None
    raw_material_id: int | None
    item_code: str
    unit_of_measure: str
    lot_code: str
    quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal


class SalesOrder(ReadModel):
    id: int
    code: str = Field(examples=["SO-0001"])
    customer_id: int
    order_date: date
    required_date: date
    status: str


class SalesLine(ReadModel):
    id: int
    line_number: int
    product_id: int
    quantity: Decimal
    unit_price_gbp: Decimal


class SalesDetail(SalesOrder):
    lines: list[SalesLine]


class PurchaseOrder(ReadModel):
    id: int
    code: str
    supplier_id: int
    order_date: date
    expected_date: date
    status: str


class ProductionOrder(ReadModel):
    id: int
    code: str
    product_id: int
    bom_id: int
    sales_order_line_id: int | None
    planned_quantity: Decimal
    planned_start: date
    planned_end: date
    status: str


class Batch(ReadModel):
    id: int
    code: str
    production_order_id: int
    product_id: int
    actual_quantity: Decimal
    status: str


class Quality(ReadModel):
    id: int
    production_batch_id: int
    inspected_at: datetime
    test_code: str
    measured_value: Decimal
    unit_of_measure: str
    result: str


class Shipment(ReadModel):
    id: int
    code: str
    warehouse_id: int
    shipped_at: datetime | None
    status: str
    tracking_reference: str | None


class EtlRun(ReadModel):
    id: int
    code: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    rows_read: int
    rows_loaded: int
    rows_rejected: int


class DataQualityIssue(ReadModel):
    id: int
    etl_run_id: int
    entity_name: str
    rule_code: str
    severity: str
    message: str
    status: str
    source_system: str
    created_at: datetime


class Consumption(ReadModel):
    id: int
    raw_material_id: int
    material_code: str
    unit_of_measure: str
    quantity: Decimal
    supplier_lot_code: str
    purchase_order_line_id: int
    purchase_order_id: int
    purchase_order_code: str
    supplier_id: int
    supplier_code: str
    source_system: str
    source_record_id: str | None


class BatchTrace(Batch):
    inspections: list[Quality]
    materials: list[Consumption]


class ProductionTrace(ProductionOrder):
    batches: list[BatchTrace]


class ShipmentTrace(Shipment):
    shipment_line_id: int
    production_batch_id: int
    quantity: Decimal


class LineTrace(SalesLine):
    product: Product
    production_orders: list[ProductionTrace]
    shipments: list[ShipmentTrace]


class OrderTrace(SalesOrder):
    customer: Master
    lines: list[LineTrace]


class QuantityKpi(BaseModel):
    metric: Literal[
        "sales_ordered",
        "sales_shipped",
        "inventory_on_hand",
        "inventory_available",
        "production_planned",
        "production_actual",
        "procurement_ordered",
        "material_consumed",
    ]
    item_type: Literal["product", "raw_material"]
    unit_of_measure: str
    quantity: Decimal


class OperationsKpis(BaseModel):
    order_count: int
    shipment_count: int
    production_batch_count: int
    inspected_batch_count: int
    passed_batch_count: int
    batch_qc_pass_rate_pct: Decimal | None = Field(
        description="All recorded tests pass; null if no inspected batches"
    )
    etl_successful_runs: int
    etl_failed_runs: int
    etl_rows_extracted: int
    etl_rows_accepted: int
    etl_rows_rejected: int
    etl_acceptance_rate_pct: Decimal | None
    etl_rejection_rate_pct: Decimal | None
    data_quality_issue_count: int
    quantities: list[QuantityKpi]
