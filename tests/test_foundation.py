from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.schema import CreateIndex, CreateTable

from api.main import create_app
from api.services import health as health_service
from api.services.health import database_status
from database.config import Settings
from database.models import (
    Base,
    BatchMaterialConsumption,
    BillOfMaterial,
    Inventory,
    InventoryTransaction,
    Product,
    ProductionBatch,
    ProductionOrder,
    PurchaseOrder,
    PurchaseOrderLine,
    RawMaterial,
    SalesOrder,
    SalesOrderLine,
    Shipment,
    ShipmentLine,
)
from database.seed import master_data, seed_master_data


@pytest.mark.parametrize("state,code", [("up", 200), ("down", 503), ("unconfigured", 503)])
def test_health_contract(state, code):
    app = create_app()
    app.dependency_overrides[database_status] = lambda: state
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == code
    assert response.json()["database"] == state
    assert response.json()["status"] == ("ok" if code == 200 else "degraded")
    assert set(response.json()) == {"application", "environment", "status", "database"}


def test_missing_database_configuration(monkeypatch):
    monkeypatch.setattr(
        health_service, "get_settings", lambda: Settings(_env_file=None, postgres_password="")
    )
    assert database_status() == "unconfigured"


def test_database_failure_is_sanitized(monkeypatch):
    monkeypatch.setattr(
        health_service,
        "get_settings",
        lambda: Settings(_env_file=None, postgres_password="synthetic-test-only"),
    )

    def fail():
        raise OperationalError("private connection information", {}, Exception("test failure"))

    monkeypatch.setattr(health_service, "get_engine", fail)
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "down"
    assert "private" not in response.text


def test_database_probe_success(monkeypatch, session):
    monkeypatch.setattr(
        health_service,
        "get_settings",
        lambda: Settings(_env_file=None, postgres_password="synthetic-test-only"),
    )
    monkeypatch.setattr(health_service, "get_engine", lambda: session.get_bind().engine)
    assert database_status() == "up"


def test_settings_environment_and_secret(monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "5544")
    settings = Settings(_env_file=None, postgres_password="test-only@:/?#")
    assert settings.postgres_port == 5544
    assert settings.database_url().password == "test-only@:/?#"
    assert "test-only" not in repr(settings)
    assert "test-only" not in str(settings.database_url())
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        Settings(_env_file=None, postgres_password="").database_url()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_port=70000)


def test_schema_contract_and_postgres_compilation():
    expected = {
        "products",
        "raw_materials",
        "suppliers",
        "customers",
        "warehouses",
        "inventory",
        "inventory_transactions",
        "bills_of_material",
        "bill_of_material_lines",
        "sales_orders",
        "sales_order_lines",
        "purchase_orders",
        "purchase_order_lines",
        "production_orders",
        "production_batches",
        "batch_material_consumption",
        "quality_inspections",
        "shipments",
        "shipment_lines",
        "demand_forecasts",
        "reorder_recommendations",
        "etl_runs",
        "data_quality_issues",
    }
    assert set(Base.metadata.tables) == expected | {
        "planning_policies",
        "planning_runs",
        "demand_observations",
        "forecast_runs",
        "forecast_metrics",
        "forecast_backtests",
        "production_resources",
        "production_policies",
        "production_plan_runs",
        "production_plan_lines",
        "production_capacity_results",
        "production_material_results",
    }
    for table in Base.metadata.sorted_tables:
        names = [constraint.name for constraint in table.constraints]
        assert len(names) == len(set(names)), f"Duplicate constraint names in {table.name}"
        assert {"id", "created_at", "updated_at", "source_system", "source_record_id"} <= set(
            table.columns.keys()
        )
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "TIMESTAMP WITH TIME ZONE" in ddl
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=postgresql.dialect()))


def test_seed_determinism_and_idempotence(session):
    assert master_data() == master_data()
    first = master_data()
    first["products"][0]["name"] = "changed"
    assert first != master_data()
    counts = seed_master_data(session)
    session.commit()
    assert counts == {
        "suppliers": 3,
        "customers": 3,
        "warehouses": 2,
        "products": 4,
        "raw_materials": 4,
        "bills_of_material": 4,
        "bill_of_material_lines": 16,
    }
    assert seed_master_data(session) == {}
    assert session.scalar(select(func.count()).select_from(Product)) == 4
    assert session.scalar(select(Product)).created_at is not None
    for bom in master_data()["boms"]:
        assert sum(line["quantity"] for line in bom["lines"]) == bom["output_quantity"]


@pytest.mark.parametrize(
    "values",
    [
        {"product_id": 1, "raw_material_id": 1, "quantity": 1},
        {"quantity": 1},
        {"product_id": 1, "quantity": -1},
        {"product_id": 1, "quantity": 1, "reserved_quantity": 2},
        {"product_id": 999, "quantity": 1},
    ],
)
def test_inventory_rejects_invalid_rows(session, values):
    seed_master_data(session)
    session.add(Inventory(warehouse_id=1, lot_code="SYN-LOT-001", **values))
    with pytest.raises(IntegrityError):
        session.flush()


def test_inventory_lot_unique_and_decimal(session):
    seed_master_data(session)
    session.add(
        Inventory(warehouse_id=1, product_id=1, lot_code="SYN-LOT", quantity=Decimal("1.25"))
    )
    session.flush()
    assert session.scalar(select(Inventory)).quantity == Decimal("1.25")
    session.add(Inventory(warehouse_id=1, product_id=1, lot_code="SYN-LOT", quantity=1))
    with pytest.raises(IntegrityError):
        session.flush()


def test_source_key_unique(session):
    session.add_all(
        [
            Product(
                code=f"SYN-{i}", name="Synthetic", source_system="test", source_record_id="same"
            )
            for i in (1, 2)
        ]
    )
    with pytest.raises(IntegrityError):
        session.flush()


def traceability_fixture(session):
    seed_master_data(session)
    day = date(2026, 1, 1)
    session.add(SalesOrder(id=1, code="SYN-SO", customer_id=1, order_date=day, required_date=day))
    session.add(
        PurchaseOrder(id=1, code="SYN-PO", supplier_id=1, order_date=day, expected_date=day)
    )
    session.flush()
    session.add(
        SalesOrderLine(
            id=1, sales_order_id=1, line_number=1, product_id=1, quantity=100, unit_price_gbp=10
        )
    )
    session.add(
        PurchaseOrderLine(
            id=1,
            purchase_order_id=1,
            line_number=1,
            raw_material_id=1,
            quantity=100,
            unit_price_gbp=1,
        )
    )
    session.flush()
    session.add(
        ProductionOrder(
            id=1,
            code="SYN-PROD",
            product_id=1,
            bom_id=1,
            sales_order_line_id=1,
            planned_quantity=100,
            planned_start=day,
            planned_end=day,
        )
    )
    session.flush()
    session.add(ProductionBatch(id=1, code="SYN-BATCH", production_order_id=1, product_id=1))
    session.add(Shipment(id=1, code="SYN-SHIP", warehouse_id=2))
    session.flush()


def test_valid_traceability_chain(session):
    traceability_fixture(session)
    session.add(
        BatchMaterialConsumption(
            production_batch_id=1,
            raw_material_id=1,
            purchase_order_line_id=1,
            supplier_lot_code="SYN-LOT",
            quantity=25,
        )
    )
    session.add(
        ShipmentLine(
            shipment_id=1, sales_order_line_id=1, production_batch_id=1, product_id=1, quantity=10
        )
    )
    session.commit()
    supplier = session.scalar(
        select(PurchaseOrder.supplier_id)
        .join(PurchaseOrderLine, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .join(
            BatchMaterialConsumption,
            BatchMaterialConsumption.purchase_order_line_id == PurchaseOrderLine.id,
        )
        .where(BatchMaterialConsumption.production_batch_id == 1)
    )
    assert supplier == 1


@pytest.mark.parametrize("kind", ["bom", "batch", "consumption", "shipment"])
def test_traceability_rejects_mismatched_items(session, kind):
    traceability_fixture(session)
    if kind == "bom":
        session.get(ProductionOrder, 1).bom_id = 2
    elif kind == "batch":
        session.get(ProductionBatch, 1).product_id = 2
    elif kind == "consumption":
        session.add(
            BatchMaterialConsumption(
                production_batch_id=1,
                raw_material_id=2,
                purchase_order_line_id=1,
                supplier_lot_code="SYN-LOT",
                quantity=1,
            )
        )
    else:
        session.add(
            ShipmentLine(
                shipment_id=1,
                sales_order_line_id=1,
                production_batch_id=1,
                product_id=2,
                quantity=1,
            )
        )
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize("kind", ["bom_quantity", "material_category", "transaction_direction"])
def test_domain_constraints(session, kind):
    seed_master_data(session)
    if kind == "bom_quantity":
        session.get(BillOfMaterial, 1).output_quantity = 0
    elif kind == "material_category":
        session.get(RawMaterial, 1).category = "unknown"
    else:
        from datetime import UTC, datetime

        session.add(Inventory(id=1, warehouse_id=1, product_id=1, lot_code="SYN", quantity=1))
        session.flush()
        session.add(
            InventoryTransaction(
                inventory_id=1,
                quantity_delta=-1,
                transaction_type="receipt",
                occurred_at=datetime.now(UTC),
                reference="SYN-RECEIPT",
            )
        )
    with pytest.raises(IntegrityError):
        session.flush()
