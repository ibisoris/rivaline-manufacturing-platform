"""Read-only APIs and aggregate correctness against SQLite and opt-in PostgreSQL."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateSchema

from analytics.queries import VIEW_NAMES, operations_kpis
from api.dependencies import read_session
from api.main import create_app
from api.services.health import database_status
from database import models as m
from database.seed import seed_master_data
from database.session import get_engine
from etl.fixtures import generate
from etl.pipeline import run_pipeline
from etl.reconcile import business_snapshot


@pytest.fixture
def reporting_session(session):
    if session.get_bind().dialect.name == "sqlite":
        engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        m.Base.metadata.create_all(engine)
        with Session(engine) as local:
            install_views(local)
            yield local
        engine.dispose()
    else:
        connection = session.connection()
        schema = connection.get_execution_options()["schema_translate_map"][None]
        connection.execute(
            text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
        )
        install_views(session)
        yield session


def install_views(session):
    sql = Path("database/migrations/versions/0002_reporting.sql").read_text()
    for statement in sql.split(";"):
        if statement.strip():
            session.execute(text(statement))
    session.commit()


def test_operational_api_and_lineage(reporting_session, tmp_path):
    session = reporting_session
    seed_master_data(session)
    session.commit()
    root = tmp_path / "legacy"
    generate(root)
    run_pipeline(session, root, tmp_path / "quarantine")
    expected_view_counts = {
        "vw_inventory_position": 32,
        "vw_order_fulfilment": 48,
        "vw_production_performance": 48,
        "vw_quality_performance": 48,
        "vw_supplier_material_flow": 192,
        "vw_operations_kpis": 1,
    }
    for name, count in expected_view_counts.items():
        assert session.scalar(text(f"SELECT count(*) FROM {name}")) == count
    assert session.scalar(text("SELECT sum(issue_count) FROM vw_data_quality_summary")) == 48
    before = business_snapshot(session)
    app = create_app()
    app.dependency_overrides[read_session] = lambda: session
    app.dependency_overrides[database_status] = lambda: "up"
    with TestClient(app) as client:
        assert client.get("/health").json()["database"] == "up"
        expected = {
            "products": 4,
            "raw-materials": 4,
            "suppliers": 3,
            "customers": 3,
            "inventory": 32,
            "sales-orders": 48,
            "purchase-orders": 192,
            "production-orders": 48,
            "production-batches": 48,
            "quality-inspections": 48,
            "shipments": 48,
            "etl-runs": 1,
            "data-quality-issues": 48,
        }
        for path, count in expected.items():
            response = client.get("/api/v1/" + path, params={"limit": 2, "offset": 0})
            assert response.status_code == 200, (path, response.text)
            payload = response.json()
            assert payload["total"] == count and len(payload["items"]) == min(2, count)
            assert [item["id"] for item in payload["items"]] == sorted(
                item["id"] for item in payload["items"]
            )
        assert "details" not in client.get("/api/v1/data-quality-issues").json()["items"][0]
        assert client.get("/api/v1/products?offset=4").json()["items"] == []
        page = client.get("/api/v1/products?limit=1&offset=1").json()
        assert page["items"][0]["code"] == "SYN-FG-002" and page["total"] == 4
        assert client.get("/api/v1/products?active=false").json()["total"] == 0
        assert client.get("/api/v1/sales-orders?status=cancelled").json()["total"] == 0
        assert client.get("/api/v1/sales-orders?customer_id=1&product_id=1").json()["total"] == 4
        assert client.get("/api/v1/purchase-orders?supplier_id=2").json()["total"] == 48
        assert client.get("/api/v1/inventory?warehouse_id=1&raw_material_id=1").json()["total"] == 4
        assert (
            client.get("/api/v1/sales-orders?date_from=2026-01-02&date_to=2026-01-02").json()[
                "total"
            ]
            == 1
        )
        assert (
            client.get("/api/v1/shipments?date_from=2026-01-06&date_to=2026-01-06").json()["total"]
            == 1
        )
        assert client.get("/api/v1/quality-inspections?result=fail").json()["total"] == 0
        assert (
            client.get("/api/v1/production-batches?product_id=1&status=released").json()["total"]
            == 12
        )
        assert (
            client.get("/api/v1/data-quality-issues?source_system=legacy_sales").json()["total"]
            == 8
        )
        for path in ("inventory/999999", "sales-orders/999999", "traceability/order/999999"):
            assert client.get("/api/v1/" + path).status_code == 404
        for path in (
            "products?limit=0",
            "products?limit=201",
            "products?offset=-1",
            "sales-orders?status=unknown",
            "sales-orders?date_from=bad",
            "sales-orders?customer_id=0",
            "sales-orders?date_from=2026-02-01&date_to=2026-01-01",
            "inventory/0",
            "inventory/not-an-id",
            "products?sql=DELETE",
            "quality-inspections?result=unknown",
        ):
            assert client.get("/api/v1/" + path).status_code == 422, path
        assert client.post("/api/v1/products", json={"name": "not written"}).status_code == 405
        assert client.delete("/api/v1/sales-orders/1").status_code == 405
        stock = client.get("/api/v1/inventory/1").json()
        assert Decimal(stock["available_quantity"]) == 500 and stock["unit_of_measure"] == "kg"
        detail = client.get("/api/v1/sales-orders/1").json()
        assert detail["code"] == "SO-0001" and len(detail["lines"]) == 1
        lineage = client.get("/api/v1/traceability/order/1").json()
        line = lineage["lines"][0]
        batch = line["production_orders"][0]["batches"][0]
        assert lineage["customer"]["code"] == "SYN-CUS-001"
        assert line["product"]["code"] == "SYN-FG-001"
        assert batch["inspections"][0]["result"] == "pass" and len(batch["materials"]) == 4
        assert batch["materials"][0]["supplier_code"] == "SYN-SUP-001"
        assert line["shipments"][0]["code"] == "SHIP-0001"
        kpi = client.get("/api/v1/kpis/operations")
        assert kpi.status_code == 200, kpi.text
        kpi = kpi.json()
        assert kpi["order_count"] == 48 and kpi["shipment_count"] == 48
        assert Decimal(kpi["batch_qc_pass_rate_pct"]) == 100
        assert Decimal(kpi["etl_acceptance_rate_pct"]) == Decimal("89.655172")
        assert kpi["etl_rows_accepted"] == 416 and kpi["data_quality_issue_count"] == 48
        quantities = {
            (r["metric"], r["item_type"], r["unit_of_measure"]): Decimal(r["quantity"])
            for r in kpi["quantities"]
        }
        assert quantities[("sales_ordered", "product", "kg")] == 9200
        assert quantities[("material_consumed", "raw_material", "kg")] == 9200
        assert quantities[("inventory_on_hand", "raw_material", "kg")] == 8000
        assert business_snapshot(session) == before

        # Empty/partial relationships stay empty rather than being fabricated.
        pending = m.SalesOrder(
            code="SYN-PARTIAL",
            customer_id=1,
            order_date=date(2026, 3, 1),
            required_date=date(2026, 3, 2),
        )
        session.add(pending)
        session.flush()
        assert client.get(f"/api/v1/traceability/order/{pending.id}").json()["lines"] == []
        partial_line = m.SalesOrderLine(
            sales_order_id=pending.id, line_number=1, product_id=1, quantity=10, unit_price_gbp=1
        )
        session.add(partial_line)
        session.flush()
        partial = client.get(f"/api/v1/traceability/order/{pending.id}").json()["lines"][0]
        assert partial["production_orders"] == [] and partial["shipments"] == []

        # Multiple batches and inspections do not add per-row SELECTs.
        statements = []
        engine = session.get_bind().engine

        def record(_, __, statement, *args):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            assert client.get("/api/v1/traceability/order/1").status_code == 200
            assert len(statements) == 7
            statements.clear()
            assert client.get("/api/v1/sales-orders/1").status_code == 200
            assert len(statements) <= 2
            for index in range(4):
                session.add(
                    m.ProductionBatch(
                        code=f"SYN-EXTRA-{index}",
                        production_order_id=1,
                        product_id=1,
                        actual_quantity=10,
                        status="pending",
                    )
                )
            session.flush()
            statements.clear()
            result = client.get("/api/v1/traceability/order/1")
            assert result.status_code == 200 and len(statements) == 7
            assert len(result.json()["lines"][0]["production_orders"][0]["batches"]) == 5
        finally:
            event.remove(engine, "before_cursor_execute", record)


def test_view_grains_and_edge_cases(reporting_session):
    session = reporting_session
    empty = operations_kpis(session)
    assert empty["order_count"] == 0 and empty["quantities"] == []
    assert empty["batch_qc_pass_rate_pct"] is None and empty["etl_acceptance_rate_pct"] is None
    seed_master_data(session)
    session.flush()
    day = date(2026, 1, 1)
    now = datetime(2026, 1, 3, tzinfo=UTC)
    session.add(
        m.SalesOrder(id=1, code="SYN-EDGE", customer_id=1, order_date=day, required_date=day)
    )
    session.add(
        m.PurchaseOrder(id=1, code="SYN-EDGE", supplier_id=1, order_date=day, expected_date=day)
    )
    session.flush()
    session.add(
        m.SalesOrderLine(
            id=1, sales_order_id=1, line_number=1, product_id=1, quantity=100, unit_price_gbp=1
        )
    )
    session.add(
        m.PurchaseOrderLine(
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
        m.ProductionOrder(
            id=1,
            code="SYN-EDGE",
            product_id=1,
            bom_id=1,
            sales_order_line_id=1,
            planned_quantity=100,
            planned_start=day,
            planned_end=day,
        )
    )
    session.flush()
    for index in (1, 2):
        session.add(
            m.ProductionBatch(
                id=index,
                code=f"SYN-B{index}",
                production_order_id=1,
                product_id=1,
                actual_quantity=50,
                status="released",
            )
        )
        session.add(
            m.Shipment(
                id=index, code=f"SYN-S{index}", warehouse_id=2, shipped_at=now, status="delivered"
            )
        )
    session.add(m.Shipment(id=3, code="SYN-CANCELLED", warehouse_id=2, status="cancelled"))
    session.flush()
    for index in (1, 2):
        session.add(
            m.BatchMaterialConsumption(
                production_batch_id=index,
                raw_material_id=1,
                purchase_order_line_id=1,
                supplier_lot_code="SYN-LOT",
                quantity=25,
            )
        )
        session.add(
            m.ShipmentLine(
                shipment_id=index,
                sales_order_line_id=1,
                production_batch_id=index,
                product_id=1,
                quantity=30,
            )
        )
    session.add(
        m.ShipmentLine(
            shipment_id=3, sales_order_line_id=1, production_batch_id=1, product_id=1, quantity=99
        )
    )
    for batch, result in [(1, "pass"), (1, "pass"), (2, "pass"), (2, "fail")]:
        session.add(
            m.QualityInspection(
                production_batch_id=batch,
                inspected_at=now,
                test_code="SYN-Q",
                measured_value=1,
                unit_of_measure="score",
                result=result,
            )
        )
    session.add(
        m.Inventory(
            warehouse_id=1, raw_material_id=1, lot_code="SYN-L", quantity=10, reserved_quantity=3
        )
    )
    session.add(
        m.Product(id=5, code="SYN-LITRES", name="Synthetic other unit", unit_of_measure="L")
    )
    session.flush()
    session.add(m.Inventory(warehouse_id=2, product_id=5, lot_code="SYN-L", quantity=5))
    session.add(
        m.EtlRun(
            code="SYN-OK",
            started_at=now,
            finished_at=now,
            status="succeeded",
            rows_read=10,
            rows_loaded=8,
            rows_rejected=2,
        )
    )
    session.add(
        m.EtlRun(
            code="SYN-FAILED",
            started_at=now,
            finished_at=now,
            status="failed",
            rows_read=100,
            rows_loaded=0,
            rows_rejected=0,
        )
    )
    session.flush()
    order = session.execute(text("SELECT * FROM vw_order_fulfilment")).mappings().one()
    assert order["ordered_quantity"] == 100 and order["shipped_quantity"] == 60
    assert order["outstanding_quantity"] == 40 and order["shipment_count"] == 2
    production = session.execute(text("SELECT * FROM vw_production_performance")).mappings().one()
    assert production["planned_quantity"] == 100 and production["actual_quantity"] == 100
    assert production["batch_count"] == 2 and production["passed_batches"] == 1
    flow = session.execute(text("SELECT * FROM vw_supplier_material_flow")).mappings().one()
    assert flow["ordered_quantity"] == 100 and flow["consumed_quantity"] == 50
    assert flow["consuming_batches"] == 2 and flow["order_marked_received"] == 0
    kpi = operations_kpis(session)
    assert kpi["batch_qc_pass_rate_pct"] == 50 and kpi["etl_acceptance_rate_pct"] == 80
    assert kpi["etl_failed_runs"] == 1 and kpi["etl_rows_extracted"] == 10
    quantities = {
        (r["metric"], r["item_type"], r["unit_of_measure"]): r["quantity"]
        for r in kpi["quantities"]
    }
    assert quantities[("inventory_available", "raw_material", "kg")] == 7
    assert quantities[("inventory_available", "product", "L")] == 5
    session.get(m.ShipmentLine, 1).quantity = 120
    session.flush()
    order = session.execute(text("SELECT * FROM vw_order_fulfilment")).mappings().one()
    assert order["outstanding_quantity"] == 0 and order["over_shipped_quantity"] == 50


def test_openapi_and_sanitized_unavailability(monkeypatch):
    from api import dependencies

    def unavailable():
        raise OperationalError("private connection detail", {}, Exception("sensitive"))

    monkeypatch.setattr(dependencies, "get_engine", unavailable)
    with TestClient(create_app()) as client:
        assert client.get("/docs").status_code == 200
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert len(schema["paths"]) == 27
        assert schema["info"]["version"] == "0.5.0"
        for operations in schema["paths"].values():
            assert set(operations) == {"get"}
            assert operations["get"]["summary"] and operations["get"]["responses"]["200"]
        failed = client.get("/api/v1/products")
        assert failed.status_code == 503
        assert "private" not in failed.text and "sensitive" not in failed.text


def test_reporting_migration_roundtrip(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Use --postgres for live reporting migration and read-only transaction tests")
    schema = "phase1_test_" + uuid4().hex
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(CreateSchema(schema))
            connection.execute(
                text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
            )
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0001_phase1")
            with Session(connection, join_transaction_mode="create_savepoint") as session:
                seed_master_data(session)
                session.commit()
                before = business_snapshot(session)
                command.upgrade(config, "0002_reporting")
                assert set(inspect(connection).get_view_names(schema=schema)) == set(VIEW_NAMES)
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0002_reporting"
                )
                assert business_snapshot(session) == before
                assert operations_kpis(session)["order_count"] == 0
                command.downgrade(config, "0001_phase1")
                assert inspect(connection).get_view_names(schema=schema) == []
                assert business_snapshot(session) == before
                command.upgrade(config, "0002_reporting")
                assert len(inspect(connection).get_view_names(schema=schema)) == 8
        finally:
            transaction.rollback()
    provider = read_session()
    session = next(provider)
    try:
        assert session.scalar(text("SHOW transaction_read_only")) == "on"
        assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
    finally:
        provider.close()
