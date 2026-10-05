"""Deterministic Phase 4 evaluation on SQLite and real isolated PostgreSQL schemas."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from test_api_analytics import reporting_session  # noqa: F401

from api.dependencies import read_session
from api.main import create_app
from api.services.health import database_status
from database import models as m
from database.seed import seed_master_data
from database.session import get_engine
from etl.reconcile import business_snapshot
from planning.contracts import ScenarioQuery
from planning.inventory import (
    PlanningError,
    explode,
    generate,
    positions,
    recommendations,
    requirements,
    scenario,
)
from planning.policies import seed_policies


@pytest.fixture
def planning_session(reporting_session):  # noqa: F811
    session = reporting_session
    for statement in (
        Path("database/migrations/versions/0003_planning.sql")
        .read_text(encoding="utf-8-sig")
        .split(";")
    ):
        if statement.strip():
            session.execute(text(statement))
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("DROP VIEW vw_material_requirements"))
    sql = Path("database/migrations/versions/0004_fractional_bom.sql").read_text()
    if session.get_bind().dialect.name == "postgresql":
        sql = sql.replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1)
    session.execute(text(sql))
    seed_master_data(session)
    session.commit()
    return session


def setup_case(session, stock=100, required=0, incoming=0, minimum=0, reserved=0):
    session.add(
        m.PlanningPolicy(
            raw_material_id=1,
            warehouse_id=1,
            unit_of_measure="kg",
            safety_stock=20,
            reorder_point=50,
            target_stock=100,
            minimum_order_quantity=minimum,
        )
    )
    session.add(
        m.Inventory(
            raw_material_id=1,
            warehouse_id=1,
            lot_code="SYN-CASE",
            quantity=stock,
            reserved_quantity=reserved,
        )
    )
    if required:
        session.add(
            m.ProductionOrder(
                code="SYN-NEED",
                product_id=1,
                bom_id=1,
                planned_quantity=required * 4,
                planned_start=date(2026, 1, 1),
                planned_end=date(2026, 1, 1),
                status="released",
            )
        )
    if incoming:
        order = m.PurchaseOrder(
            code="SYN-INCOMING",
            supplier_id=1,
            order_date=date(2026, 1, 1),
            expected_date=date(2026, 1, 2),
            status="confirmed",
        )
        session.add(order)
        session.flush()
        session.add(
            m.PurchaseOrderLine(
                purchase_order_id=order.id,
                raw_material_id=1,
                line_number=1,
                quantity=incoming,
                unit_price_gbp=1,
            )
        )
    session.flush()


def first(session):
    return next(p for p in positions(session) if p.item_type == "raw_material" and p.item_id == 1)


@pytest.mark.parametrize(
    "stock,required,incoming,minimum,projected,shortage,proposal,status",
    [
        (100, 0, 0, 0, 100, 0, 0, "healthy"),
        (40, 0, 0, 0, 40, 0, 60, "below_reorder"),
        (30, 80, 0, 0, -50, 50, 150, "shortage"),
        (25, 100, 0, 0, -75, 75, 175, "shortage"),
        (30, 80, 150, 0, 100, 0, 0, "healthy"),
        (40, 0, 0, 200, 40, 0, 200, "below_reorder"),
        (10, 0, 0, 0, 10, 0, 90, "below_safety"),
        (50, 0, 0, 0, 50, 0, 0, "at_reorder"),
    ],
)
def test_known_evaluation(
    planning_session, stock, required, incoming, minimum, projected, shortage, proposal, status
):
    session = planning_session
    setup_case(session, stock, required, incoming, minimum)
    result = first(session)
    assert result.projected_quantity == projected
    assert result.shortage_quantity == shortage
    assert result.recommended_quantity == proposal
    assert result.risk_status == status
    assert "projected stock" in result.explanation
    if proposal:
        assert "restore target" in result.explanation and "minimum order" in result.explanation
    needs = requirements(session)
    assert len(needs) == (4 if required else 0)
    assert all(r.required_quantity == required for r in needs)
    assert len({(r.production_order_id, r.raw_material_id) for r in needs}) == len(needs)
    assert len(positions(session)) == 8
    assert session.scalar(text("SELECT count(*) FROM vw_inventory_risk")) == 8


def test_what_if_replay_and_history(planning_session):
    session = planning_session
    setup_case(session, stock=100)
    before = business_snapshot(session)
    result = scenario(session, ScenarioQuery(product_id=1, quantity=800, unit_of_measure="kg"))
    material = result.materials[0]
    assert material.incremental_requirement == 200
    assert material.baseline_projected == 100 and material.scenario_projected == -100
    assert material.shortage_quantity == material.additional_shortage == 100
    assert material.recommended_quantity == 200
    assert business_snapshot(session) == before
    assert result.persisted is False
    run, created = generate(session)
    assert (
        created and session.scalar(select(func.count()).select_from(m.ReorderRecommendation)) == 0
    )
    repeated, created = generate(session)
    assert not created and repeated.id == run.id
    session.scalar(select(m.Inventory)).quantity = 40
    session.flush()
    changed, created = generate(session)
    assert created and changed.code != run.code
    item = recommendations(session)[0]
    assert item.quantity == 60 and item.input_position.on_hand_quantity == 40
    assert session.scalar(text("SELECT count(*) FROM vw_reorder_recommendations")) == 1
    row = session.scalar(select(m.ReorderRecommendation))
    row.status = "dismissed"
    session.flush()
    assert not generate(session)[1]
    assert row.status == "dismissed"
    session.scalar(select(m.Inventory)).quantity = 100
    session.flush()
    assert generate(session)[0].id == run.id
    assert item.input_position.on_hand_quantity == 40
    assert session.scalar(select(func.count()).select_from(m.PlanningRun)) == 2


def test_reservations_consumption_statuses_and_units(planning_session):
    session = planning_session
    setup_case(session, stock=100, required=100, incoming=50, reserved=10)
    # Additional lot and warehouse must aggregate once, not multiply BOM needs.
    session.add(m.Inventory(raw_material_id=1, warehouse_id=2, lot_code="SYN-SECOND", quantity=20))
    order = session.scalar(select(m.ProductionOrder))
    batch = m.ProductionBatch(
        code="SYN-PARTIAL", production_order_id=order.id, product_id=1, actual_quantity=100
    )
    session.add(batch)
    session.flush()
    purchase_line = session.scalar(select(m.PurchaseOrderLine))
    session.add(
        m.BatchMaterialConsumption(
            production_batch_id=batch.id,
            raw_material_id=1,
            purchase_order_line_id=purchase_line.id,
            supplier_lot_code="SYN-USED",
            quantity=25,
        )
    )
    session.flush()
    assert first(session).required_quantity == 75
    assert first(session).projected_quantity == 85  # 120 - 10 + 50 - 75
    for state in ("open", "received", "cancelled"):
        session.scalar(select(m.PurchaseOrder)).status = state
        session.flush()
        assert first(session).incoming_quantity == 0
    for state in ("completed", "cancelled"):
        order.status = state
        session.flush()
        assert requirements(session) == []
    session.get(m.RawMaterial, 1).unit_of_measure = "L"
    session.flush()
    assert first(session).risk_status == "invalid_policy"
    with pytest.raises(PlanningError, match="unit mismatch"):
        generate(session)
    # Component unit is independent of product unit; no density conversion is inferred.
    result = scenario(session, ScenarioQuery(product_id=1, quantity=100, unit_of_measure="kg"))
    assert result.materials[0].unit_of_measure == "L"
    assert result.materials[0].incremental_requirement == 25
    assert result.materials[0].recommended_quantity is None
    with pytest.raises(PlanningError, match="canonical unit"):
        scenario(session, ScenarioQuery(product_id=1, quantity=100, unit_of_measure="L"))
    assert explode(D("1"), D("3"), D("1")) == D("0.333333")


def test_policy_seed_and_constraints(planning_session):
    session = planning_session
    assert seed_policies(session) == 4
    assert seed_policies(session) == 0
    policy = session.scalar(select(m.PlanningPolicy))
    policy.safety_stock = 400
    session.flush()
    with pytest.raises(PlanningError, match="overwrite"):
        seed_policies(session)
    policy.reorder_point = -1
    with pytest.raises(IntegrityError):
        session.flush()


def test_planning_api(planning_session):
    session = planning_session
    setup_case(session, stock=40, required=100)
    run, _ = generate(session)
    session.commit()
    before = business_snapshot(session)
    app = create_app()
    app.dependency_overrides[read_session] = lambda: session
    app.dependency_overrides[database_status] = lambda: "up"
    with TestClient(app) as client:
        result = client.get("/api/v1/inventory/positions?item_type=raw_material&item_id=1").json()
        assert result["total"] == 1 and D(result["items"][0]["shortage_quantity"]) == 60
        assert client.get("/api/v1/inventory/positions?shortage_only=true").json()["total"] == 4
        assert client.get("/api/v1/inventory/positions?limit=1&offset=8").json()["items"] == []
        needs = client.get("/api/v1/planning/material-requirements?raw_material_id=1").json()
        assert needs["total"] == 1
        page = client.get("/api/v1/reorder-recommendations?warehouse_id=1&status=proposed").json()
        assert page["total"] == 1
        detail = client.get("/api/v1/reorder-recommendations/" + str(page["items"][0]["id"]))
        assert detail.status_code == 200 and detail.json()["run_code"] == run.code
        assert detail.json()["affected_requirements"][0]["production_order_code"] == "SYN-NEED"
        assert client.get("/api/v1/reorder-recommendations/99999").status_code == 404
        path = "/api/v1/planning/material-availability?product_id=1&quantity=800&unit_of_measure=kg"
        response = client.get(path)
        assert response.status_code == 200 and response.json()["persisted"] is False
        assert client.get(path.replace("product_id=1", "product_id=999")).status_code == 404
        assert client.get(path.replace("measure=kg", "measure=L")).status_code == 409
        assert client.get(path.replace("quantity=800", "quantity=-1")).status_code == 422
        for suffix in ("?limit=201", "?warehouse_id=1", "?item_id=0"):
            assert client.get("/api/v1/inventory/positions" + suffix).status_code == 422
        assert client.post("/api/v1/planning/material-availability").status_code == 405
        assert len(client.get("/openapi.json").json()["paths"]) == 31
    assert business_snapshot(session) == before


def test_phase4_migration(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Use --postgres for Phase 4 migration and preservation checks")
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
            command.upgrade(config, "0002_reporting")
            with Session(connection, join_transaction_mode="create_savepoint") as session:
                seed_master_data(session)
                session.commit()
                before = business_snapshot(session)
                command.upgrade(config, "0004_fractional_bom")
                assert business_snapshot(session) == before
                assert len(inspect(connection).get_view_names(schema=schema)) == 11
                baseline = m.Base.metadata.__class__()
                for name in m.PHASE4_TABLES:
                    m.Base.metadata.tables[name].to_metadata(baseline)
                assert not compare_metadata(MigrationContext.configure(connection), baseline)
                command.downgrade(config, "0002_reporting")
                assert business_snapshot(session) == before
                assert len(inspect(connection).get_view_names(schema=schema)) == 8
                command.upgrade(config, "0004_fractional_bom")
                seed_policies(session)
                generate(session)
                session.commit()
                with pytest.raises(RuntimeError, match="archive"):
                    command.downgrade(config, "0002_reporting")
        finally:
            transaction.rollback()


def test_empty_ambiguous_bom_and_precision(planning_session):
    session = planning_session
    setup_case(session, stock=40, required=1)
    other = m.BillOfMaterial(
        code="SYN-EMPTY", product_id=1, version=2, output_quantity=100, status="active"
    )
    session.add(other)
    session.flush()
    with pytest.raises(PlanningError, match="exactly one"):
        scenario(session, ScenarioQuery(product_id=1, quantity=10, unit_of_measure="kg"))
    with pytest.raises(PlanningError, match="no material lines"):
        scenario(
            session, ScenarioQuery(product_id=1, bom_id=other.id, quantity=10, unit_of_measure="kg")
        )
    session.scalar(select(m.ProductionOrder)).bom_id = other.id
    session.flush()
    with pytest.raises(PlanningError, match="empty BOM"):
        positions(session)
    with pytest.raises(PlanningError, match="empty BOM"):
        generate(session)
    session.scalar(select(m.ProductionOrder)).bom_id = 1
    session.get(m.BillOfMaterial, 1).output_quantity = 3
    session.flush()
    assert requirements(session)[0].gross_quantity == D("33.333333")
