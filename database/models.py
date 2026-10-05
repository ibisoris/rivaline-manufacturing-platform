"""Phase 1 operational schema. Quantities use each item's canonical unit (kg for seed data)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {Decimal: Numeric(18, 6), datetime: DateTime(timezone=True)}


class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    source_system: Mapped[str] = mapped_column(String(80), default="rivaline")
    source_record_id: Mapped[str | None] = mapped_column(String(160))


class Master(Record):
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(default=True)


class Product(Master, Base):
    __tablename__ = "products"
    unit_of_measure: Mapped[str] = mapped_column(String(12), default="kg")


class Supplier(Master, Base):
    __tablename__ = "suppliers"


class RawMaterial(Master, Base):
    __tablename__ = "raw_materials"
    category: Mapped[str] = mapped_column(String(30))
    unit_of_measure: Mapped[str] = mapped_column(String(12), default="kg")
    preferred_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    __table_args__ = (
        CheckConstraint("category IN ('pigment', 'resin', 'solvent', 'additive')", name="category"),
    )


class Customer(Master, Base):
    __tablename__ = "customers"


class Warehouse(Master, Base):
    __tablename__ = "warehouses"


class Inventory(Record, Base):
    __tablename__ = "inventory"
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    raw_material_id: Mapped[int | None] = mapped_column(ForeignKey("raw_materials.id"))
    lot_code: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    reserved_quantity: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL AND raw_material_id IS NULL) OR "
            "(product_id IS NULL AND raw_material_id IS NOT NULL)",
            name="one_item",
        ),
        CheckConstraint(
            "quantity >= 0 AND reserved_quantity >= 0 AND reserved_quantity <= quantity",
            name="quantities",
        ),
        UniqueConstraint("warehouse_id", "product_id", "lot_code", name="uq_inventory_product_lot"),
        UniqueConstraint(
            "warehouse_id", "raw_material_id", "lot_code", name="uq_inventory_material_lot"
        ),
    )


class InventoryTransaction(Record, Base):
    __tablename__ = "inventory_transactions"
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"), index=True)
    quantity_delta: Mapped[Decimal]
    transaction_type: Mapped[str] = mapped_column(String(24))
    occurred_at: Mapped[datetime]
    reference: Mapped[str] = mapped_column(String(160))
    __table_args__ = (
        CheckConstraint("quantity_delta <> 0", name="nonzero"),
        CheckConstraint("transaction_type IN ('receipt', 'issue', 'adjustment')", name="type"),
        CheckConstraint(
            "transaction_type = 'adjustment' OR "
            "(transaction_type = 'receipt' AND quantity_delta > 0) OR "
            "(transaction_type = 'issue' AND quantity_delta < 0)",
            name="direction",
        ),
    )


class BillOfMaterial(Record, Base):
    __tablename__ = "bills_of_material"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    version: Mapped[int] = mapped_column(default=1)
    output_quantity: Mapped[Decimal]
    status: Mapped[str] = mapped_column(String(20), default="draft")
    __table_args__ = (
        UniqueConstraint("product_id", "version"),
        UniqueConstraint("id", "product_id"),
        CheckConstraint("output_quantity > 0 AND version > 0", name="positive"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="status"),
    )


class BillOfMaterialLine(Record, Base):
    __tablename__ = "bill_of_material_lines"
    bom_id: Mapped[int] = mapped_column(ForeignKey("bills_of_material.id"), index=True)
    raw_material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"))
    quantity: Mapped[Decimal]
    __table_args__ = (
        UniqueConstraint("bom_id", "raw_material_id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )


class SalesOrder(Record, Base):
    __tablename__ = "sales_orders"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_date: Mapped[date]
    required_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), default="open")
    __table_args__ = (
        CheckConstraint("required_date >= order_date", name="dates"),
        CheckConstraint("status IN ('open', 'confirmed', 'fulfilled', 'cancelled')", name="status"),
    )


class SalesOrderLine(Record, Base):
    __tablename__ = "sales_order_lines"
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), index=True)
    line_number: Mapped[int]
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal]
    unit_price_gbp: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    __table_args__ = (
        UniqueConstraint("sales_order_id", "line_number"),
        UniqueConstraint("id", "product_id"),
        CheckConstraint("quantity > 0 AND unit_price_gbp >= 0 AND line_number > 0", name="values"),
    )


class PurchaseOrder(Record, Base):
    __tablename__ = "purchase_orders"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    order_date: Mapped[date]
    expected_date: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), default="open")
    __table_args__ = (
        CheckConstraint("expected_date >= order_date", name="dates"),
        CheckConstraint("status IN ('open', 'confirmed', 'received', 'cancelled')", name="status"),
    )


class PurchaseOrderLine(Record, Base):
    __tablename__ = "purchase_order_lines"
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    line_number: Mapped[int]
    raw_material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"))
    quantity: Mapped[Decimal]
    unit_price_gbp: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line_number"),
        UniqueConstraint("id", "raw_material_id"),
        CheckConstraint("quantity > 0 AND unit_price_gbp >= 0 AND line_number > 0", name="values"),
    )


class ProductionOrder(Record, Base):
    __tablename__ = "production_orders"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    bom_id: Mapped[int]
    sales_order_line_id: Mapped[int | None]
    planned_quantity: Mapped[Decimal]
    planned_start: Mapped[date]
    planned_end: Mapped[date]
    status: Mapped[str] = mapped_column(String(20), default="planned")
    __table_args__ = (
        ForeignKeyConstraint(
            ["bom_id", "product_id"], ["bills_of_material.id", "bills_of_material.product_id"]
        ),
        ForeignKeyConstraint(
            ["sales_order_line_id", "product_id"],
            ["sales_order_lines.id", "sales_order_lines.product_id"],
        ),
        UniqueConstraint("id", "product_id"),
        CheckConstraint("planned_quantity > 0 AND planned_end >= planned_start", name="plan"),
        CheckConstraint(
            "status IN ('planned', 'released', 'completed', 'cancelled')", name="status"
        ),
    )


class ProductionBatch(Record, Base):
    __tablename__ = "production_batches"
    code: Mapped[str] = mapped_column(String(80), unique=True)
    production_order_id: Mapped[int]
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    actual_quantity: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    __table_args__ = (
        ForeignKeyConstraint(
            ["production_order_id", "product_id"],
            ["production_orders.id", "production_orders.product_id"],
        ),
        UniqueConstraint("id", "product_id"),
        CheckConstraint("actual_quantity >= 0", name="quantity"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'quarantined', 'released', 'rejected')",
            name="status",
        ),
    )


class BatchMaterialConsumption(Record, Base):
    __tablename__ = "batch_material_consumption"
    production_batch_id: Mapped[int] = mapped_column(
        ForeignKey("production_batches.id"), index=True
    )
    raw_material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"))
    purchase_order_line_id: Mapped[int]
    supplier_lot_code: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[Decimal]
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_order_line_id", "raw_material_id"],
            ["purchase_order_lines.id", "purchase_order_lines.raw_material_id"],
        ),
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )


class QualityInspection(Record, Base):
    __tablename__ = "quality_inspections"
    production_batch_id: Mapped[int] = mapped_column(
        ForeignKey("production_batches.id"), index=True
    )
    inspected_at: Mapped[datetime]
    test_code: Mapped[str] = mapped_column(String(40))
    measured_value: Mapped[Decimal]
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    result: Mapped[str] = mapped_column(String(20))
    __table_args__ = (CheckConstraint("result IN ('pass', 'fail', 'pending')", name="result"),)


class Shipment(Record, Base):
    __tablename__ = "shipments"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    shipped_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20), default="pending")
    tracking_reference: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'dispatched', 'delivered', 'cancelled')", name="status"
        ),
    )


class ShipmentLine(Record, Base):
    __tablename__ = "shipment_lines"
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    sales_order_line_id: Mapped[int]
    production_batch_id: Mapped[int]
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal]
    __table_args__ = (
        ForeignKeyConstraint(
            ["sales_order_line_id", "product_id"],
            ["sales_order_lines.id", "sales_order_lines.product_id"],
        ),
        ForeignKeyConstraint(
            ["production_batch_id", "product_id"],
            ["production_batches.id", "production_batches.product_id"],
        ),
        UniqueConstraint("shipment_id", "sales_order_line_id", "production_batch_id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )


class DemandForecast(Record, Base):
    __tablename__ = "demand_forecasts"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    period_start: Mapped[date]
    period_end: Mapped[date]
    quantity: Mapped[Decimal]
    model_version: Mapped[str] = mapped_column(String(80))
    generated_at: Mapped[datetime]
    __table_args__ = (
        UniqueConstraint(
            "product_id", "period_start", "period_end", "model_version", "generated_at"
        ),
        CheckConstraint("quantity >= 0 AND period_end >= period_start", name="forecast"),
    )


class ReorderRecommendation(Record, Base):
    __tablename__ = "reorder_recommendations"
    raw_material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    quantity: Mapped[Decimal]
    reason: Mapped[str] = mapped_column(String(500))
    generated_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("status IN ('proposed', 'accepted', 'dismissed')", name="status"),
    )


class EtlRun(Record, Base):
    __tablename__ = "etl_runs"
    code: Mapped[str] = mapped_column(String(80), unique=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20), default="running")
    rows_read: Mapped[int] = mapped_column(default=0)
    rows_loaded: Mapped[int] = mapped_column(default=0)
    rows_rejected: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status"),
        CheckConstraint(
            "rows_read >= 0 AND rows_loaded >= 0 AND rows_rejected >= 0 "
            "AND rows_loaded + rows_rejected <= rows_read",
            name="counts",
        ),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="dates"),
    )


class DataQualityIssue(Record, Base):
    __tablename__ = "data_quality_issues"
    etl_run_id: Mapped[int] = mapped_column(ForeignKey("etl_runs.id"), index=True)
    entity_name: Mapped[str] = mapped_column(String(80))
    rule_code: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="open")
    __table_args__ = (
        CheckConstraint("severity IN ('warning', 'error')", name="severity"),
        CheckConstraint("status IN ('open', 'resolved', 'accepted')", name="status"),
    )


# Frozen table-name scope for baseline migration and historical snapshot checks.
PHASE1_TABLES = frozenset(Base.metadata.tables)


class PlanningPolicy(Record, Base):
    """One pooled-stock policy per material; warehouse is the proposed delivery destination."""

    __tablename__ = "planning_policies"
    raw_material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"), unique=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    safety_stock: Mapped[Decimal]
    reorder_point: Mapped[Decimal]
    target_stock: Mapped[Decimal]
    minimum_order_quantity: Mapped[Decimal]
    __table_args__ = (
        CheckConstraint(
            "safety_stock >= 0 AND reorder_point >= safety_stock "
            "AND target_stock > reorder_point AND minimum_order_quantity >= 0",
            name="thresholds",
        ),
    )


class PlanningRun(Record, Base):
    __tablename__ = "planning_runs"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    algorithm_version: Mapped[str] = mapped_column(String(40))
    generated_at: Mapped[datetime]
    inputs: Mapped[dict] = mapped_column(JSON)


PHASE4_TABLES = frozenset(Base.metadata.tables)


class DemandObservation(Record, Base):
    """Archived synthetic demand export; deliberately separate from operational sales orders."""

    __tablename__ = "demand_observations"
    dataset_code: Mapped[str] = mapped_column(String(60), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    period_start: Mapped[date]
    quantity: Mapped[Decimal]
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    file_sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint("quantity >= 0", name="quantity"),)


class ForecastRun(Record, Base):
    __tablename__ = "forecast_runs"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    dataset_code: Mapped[str] = mapped_column(String(60))
    algorithm_version: Mapped[str] = mapped_column(String(40))
    training_cutoff: Mapped[date]
    horizon: Mapped[int]
    generated_at: Mapped[datetime]
    inputs: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (CheckConstraint("horizon = 3", name="horizon"),)


class ForecastMetric(Record, Base):
    __tablename__ = "forecast_metrics"
    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    scope_key: Mapped[str] = mapped_column(String(60))
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    model_name: Mapped[str] = mapped_column(String(30))
    evaluation_split: Mapped[str] = mapped_column(String(20))
    observations: Mapped[int]
    mae: Mapped[Decimal]
    rmse: Mapped[Decimal]
    wape_pct: Mapped[Decimal | None]
    __table_args__ = (
        UniqueConstraint("forecast_run_id", "scope_key", "model_name", "evaluation_split"),
        CheckConstraint(
            "observations > 0 AND mae >= 0 AND rmse >= 0 AND (wape_pct IS NULL OR wape_pct >= 0)",
            name="metrics",
        ),
        CheckConstraint("evaluation_split IN ('validation', 'test')", name="split"),
        CheckConstraint("model_name IN ('naive', 'moving_average', 'linear_trend')", name="model"),
    )


class ForecastBacktest(Record, Base):
    __tablename__ = "forecast_backtests"
    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    model_name: Mapped[str] = mapped_column(String(30))
    evaluation_split: Mapped[str] = mapped_column(String(20))
    training_cutoff: Mapped[date]
    period_start: Mapped[date]
    actual_quantity: Mapped[Decimal]
    predicted_quantity: Mapped[Decimal]
    __table_args__ = (
        UniqueConstraint(
            "forecast_run_id", "product_id", "model_name", "training_cutoff", "period_start"
        ),
        CheckConstraint(
            "actual_quantity >= 0 AND predicted_quantity >= 0 AND period_start > training_cutoff",
            name="values",
        ),
        CheckConstraint("evaluation_split IN ('validation', 'test')", name="split"),
        CheckConstraint("model_name IN ('naive', 'moving_average', 'linear_trend')", name="model"),
    )


PHASE5_TABLES = frozenset(Base.metadata.tables)


class ProductionResource(Record, Base):
    """Synthetic residual monthly capacity, after commitments outside this plan."""

    __tablename__ = "production_resources"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    monthly_hours: Mapped[Decimal]
    __table_args__ = (CheckConstraint("monthly_hours >= 0", name="hours"),)


class ProductionPolicy(Record, Base):
    __tablename__ = "production_policies"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("production_resources.id"))
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    minimum_batch: Mapped[Decimal]
    preferred_batch: Mapped[Decimal]
    maximum_batch: Mapped[Decimal]
    units_per_hour: Mapped[Decimal]
    priority: Mapped[int]
    __table_args__ = (
        CheckConstraint(
            "minimum_batch > 0 AND preferred_batch >= minimum_batch "
            "AND maximum_batch >= preferred_batch",
            name="batch_bounds",
        ),
        CheckConstraint("units_per_hour > 0 AND priority >= 1", name="rate_priority"),
    )


class ProductionPlanRun(Record, Base):
    __tablename__ = "production_plan_runs"
    code: Mapped[str] = mapped_column(String(64), unique=True)
    algorithm_version: Mapped[str] = mapped_column(String(40))
    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"))
    generated_at: Mapped[datetime]
    inputs: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)


class ProductionPlanLine(Record, Base):
    __tablename__ = "production_plan_lines"
    plan_run_id: Mapped[int] = mapped_column(ForeignKey("production_plan_runs.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    resource_id: Mapped[int] = mapped_column(ForeignKey("production_resources.id"))
    period_start: Mapped[date]
    product_code: Mapped[str] = mapped_column(String(40))
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    gross_demand: Mapped[Decimal]
    inventory_offset: Mapped[Decimal]
    surplus_offset: Mapped[Decimal]
    net_requirement: Mapped[Decimal]
    proposed_quantity: Mapped[Decimal]
    allocated_quantity: Mapped[Decimal]
    unmet_quantity: Mapped[Decimal]
    batch_count: Mapped[int]
    required_hours: Mapped[Decimal]
    available_hours: Mapped[Decimal]
    allocated_hours: Mapped[Decimal]
    overload_hours: Mapped[Decimal]
    utilisation_pct: Mapped[Decimal | None]
    status: Mapped[str] = mapped_column(String(40))
    explanation: Mapped[str] = mapped_column(String(2000))
    __table_args__ = (
        UniqueConstraint("plan_run_id", "product_id", "period_start"),
        CheckConstraint(
            "gross_demand >= 0 AND inventory_offset >= 0 AND surplus_offset >= 0 "
            "AND net_requirement >= 0 AND proposed_quantity >= net_requirement "
            "AND allocated_quantity >= 0 AND allocated_quantity <= proposed_quantity "
            "AND unmet_quantity >= 0 AND batch_count >= 0",
            name="quantities",
        ),
        CheckConstraint(
            "required_hours >= 0 AND available_hours >= 0 AND allocated_hours >= 0 "
            "AND allocated_hours <= available_hours AND overload_hours >= 0 "
            "AND (utilisation_pct IS NULL OR utilisation_pct >= 0)",
            name="hours",
        ),
        CheckConstraint(
            "status IN ('FEASIBLE', 'MATERIAL_CONSTRAINED', 'CAPACITY_CONSTRAINED', "
            "'MATERIAL_AND_CAPACITY_CONSTRAINED')",
            name="status",
        ),
    )


class ProductionCapacityResult(Record, Base):
    __tablename__ = "production_capacity_results"
    plan_run_id: Mapped[int] = mapped_column(ForeignKey("production_plan_runs.id"))
    resource_id: Mapped[int] = mapped_column(ForeignKey("production_resources.id"))
    resource_code: Mapped[str] = mapped_column(String(40))
    period_start: Mapped[date]
    required_hours: Mapped[Decimal]
    available_hours: Mapped[Decimal]
    allocated_hours: Mapped[Decimal]
    overload_hours: Mapped[Decimal]
    utilisation_pct: Mapped[Decimal | None]
    __table_args__ = (
        UniqueConstraint("plan_run_id", "resource_id", "period_start"),
        CheckConstraint(
            "required_hours >= 0 AND available_hours >= 0 AND allocated_hours >= 0 "
            "AND allocated_hours <= available_hours AND overload_hours >= 0 "
            "AND (utilisation_pct IS NULL OR utilisation_pct >= 0)",
            name="hours",
        ),
    )


class ProductionMaterialResult(Record, Base):
    __tablename__ = "production_material_results"
    plan_line_id: Mapped[int] = mapped_column(ForeignKey("production_plan_lines.id"))
    raw_material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"))
    material_code: Mapped[str] = mapped_column(String(40))
    unit_of_measure: Mapped[str] = mapped_column(String(12))
    required_quantity: Mapped[Decimal]
    available_quantity: Mapped[Decimal]
    shortage_quantity: Mapped[Decimal]
    allocated_quantity: Mapped[Decimal]
    remaining_quantity: Mapped[Decimal]
    __table_args__ = (
        UniqueConstraint("plan_line_id", "raw_material_id"),
        CheckConstraint(
            "required_quantity >= 0 AND available_quantity >= 0 "
            "AND shortage_quantity >= 0 AND allocated_quantity >= 0 "
            "AND allocated_quantity <= required_quantity AND remaining_quantity >= 0",
            name="quantities",
        ),
    )


# Every source record is unique within its entity when an external key is supplied.
for table in Base.metadata.tables.values():
    table.append_constraint(UniqueConstraint("source_system", "source_record_id"))
    # Cover composite references without duplicating existing leading-column indexes.
    indexed = {tuple(c.name for c in i.columns)[0] for i in table.indexes}
    for constraint in table.foreign_key_constraints:
        column = next(iter(constraint.columns))
        if column.name not in indexed:
            Index(f"ix_{table.name}_{column.name}", column)
            indexed.add(column.name)
