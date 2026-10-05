"""Deterministic production planning, independent SQLite and isolated native PostgreSQL."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from test_api_analytics import reporting_session  # noqa: F401
from test_forecasting import CUTOFF, forecast_session, load  # noqa: F401
from test_planning import planning_session  # noqa: F401

from api.dependencies import read_session
from api.main import create_app
from api.services.health import database_status
from database import models as m
from database.seed import seed_master_data
from database.session import get_engine
from planning.forecasting import generate_forecasts
from planning.inventory import PlanningError
from planning.production import batch_sizes, calculate, save_forecast_plan, seed_production_policies
from planning.production_contracts import WhatIf


@pytest.fixture
def production_session(forecast_session):  # noqa: F811
    session = forecast_session
    for sql in Path("database/migrations/versions/0006_production.sql").read_text().split(";"):
        if sql.strip():
            session.execute(text(sql))
    assert seed_production_policies(session) == 6
    assert seed_production_policies(session) == 0
    for index in range(1, 5):
        for field in ("product_id", "raw_material_id"):
            session.add(
                m.Inventory(
                    **{field: index},
                    warehouse_id=1,
                    lot_code="SYN-P6-TEST",
                    quantity=2000,
                    reserved_quantity=0,
                )
            )
    session.commit()
    return session


def demand(quantity, product=1, period="2026-11-01"):
    return dict(
        product_id=product, period_start=period, quantity=str(quantity), unit_of_measure="kg"
    )


def what(session, *demands):
    return calculate(session, request=WhatIf(demands=list(demands)))[0]


def snapshot(session):
    return json.dumps(
        {
            name: [dict(r) for r in session.execute(select(t).order_by(t.c.id)).mappings()]
            for name, t in m.Base.metadata.tables.items()
        },
        sort_keys=True,
        default=str,
    )


@pytest.mark.parametrize(
    "net,expected",
    [
        (0, []),
        (2300, [1000, 1000, 300]),
        (2100, [1000, 1000, 200]),
        (50, [200]),
        (2400, [1000, 1000, 400]),
    ],
)
def test_batch_rules(net, expected):
    actual = batch_sizes(D(net), D(200), D(1000), D(1200))
    assert actual == list(map(D, expected))
    assert all(D(200) <= q <= D(1200) for q in actual)
    assert sum(actual, D(0)) >= net
    with pytest.raises(PlanningError):
        batch_sizes(D(net), D(200), D(1000), D(500))


@pytest.mark.parametrize(
    "quantity,raw,hours,status,net,batches,shortage,overload",
    [
        (1000, 2000, 10, "FEASIBLE", 0, [], 0, 0),
        (2500, 2000, 10, "FEASIBLE", 500, [500], 0, 0),
        (3000, 100, 10, "MATERIAL_CONSTRAINED", 1000, [1000], 150, 0),
        (3500, 2000, 10, "CAPACITY_CONSTRAINED", 1500, [1000, 500], 0, 5),
        (3500, 100, 10, "MATERIAL_AND_CAPACITY_CONSTRAINED", 1500, [1000, 500], 275, 5),
        (4300, 2000, 30, "FEASIBLE", 2300, [1000, 1000, 300], 0, 0),
        (4100, 2000, 30, "FEASIBLE", 2100, [1000, 1000, 200], 0, 0),
    ],
)
def test_evaluation_scenarios(
    production_session, quantity, raw, hours, status, net, batches, shortage, overload
):
    session = production_session
    for row in session.scalars(select(m.Inventory).where(m.Inventory.raw_material_id.is_not(None))):
        row.quantity = D(raw)
    session.scalar(
        select(m.ProductionResource).where(m.ProductionResource.code == "SYN-MIX")
    ).monthly_hours = D(hours)
    session.flush()
    before = snapshot(session)
    result = what(session, demand(quantity))
    line = result.lines[0]
    assert line.status == status and line.net_requirement == net
    assert line.inventory_offset == min(quantity, 2000)
    assert [b.quantity for b in line.batches] == list(map(D, batches))
    assert line.overload_hours == overload
    assert line.required_hours == sum(batches) / 100
    assert line.utilisation_pct == (D(sum(batches)) / hours).quantize(D("0.01"))
    assert all(r.shortage_quantity == shortage for r in line.materials)
    assert all(r.required_quantity == sum(batches) / 4 for r in line.materials)
    assert result == what(session, demand(quantity))
    assert snapshot(session) == before and result.persisted is False


def test_shared_capacity_materials_priority_and_carry(production_session):
    session = production_session
    first = what(session, demand(2800, 2), demand(2800, 1))
    assert [r.product_id for r in first.lines] == [1, 2]
    assert [r.allocated_quantity for r in first.lines] == [D(800), D(0)]
    assert first.lines[1].status == "CAPACITY_CONSTRAINED"
    assert first.lines[1].available_hours == 2
    assert first.capacity[0].required_hours == 16 and first.capacity[0].overload_hours == 6
    assert first.capacity[0].utilisation_pct == 160
    assert first == what(session, demand(2800, 1), demand(2800, 2))
    # Product code is the stable final tie-breaker.
    for row in session.scalars(select(m.ProductionPolicy)):
        row.priority = 1
    session.flush()
    assert [r.product_id for r in what(session, demand(2800, 2), demand(2800, 1)).lines] == [1, 2]
    carried = what(session, demand(2100, 1, "2026-10-01"), demand(100, 1, "2026-11-01"))
    assert carried.lines[0].proposed_quantity == 200
    assert carried.lines[1].inventory_offset == 0 and carried.lines[1].surplus_offset == 100
    assert carried.lines[1].net_requirement == 0
    # Raw material is consumed once across products, even on different resources/months.
    for row in session.scalars(select(m.Inventory).where(m.Inventory.raw_material_id.is_not(None))):
        row.quantity = 200
    session.flush()
    shared = what(session, demand(2800, 1, "2026-10-01"), demand(2800, 3, "2026-11-01"))
    assert shared.lines[0].status == "FEASIBLE"
    assert shared.lines[1].status == "MATERIAL_CONSTRAINED"
    assert all(
        r.available_quantity == 0 and r.shortage_quantity == 200 for r in shared.lines[1].materials
    )


def test_input_failures_zero_capacity_and_forecast_overlap(production_session, tmp_path):
    session = production_session
    with pytest.raises(ValidationError):
        WhatIf(demands=[demand(10), demand(10)])
    for value in ("NaN", "Infinity", "-1", "0.0000001"):
        with pytest.raises(ValidationError):
            WhatIf(demands=[demand(value)])
    with pytest.raises(PlanningError, match="exactly one"):
        calculate(session)
    with pytest.raises(LookupError):
        what(session, demand(10, 999))
    bad = demand(10)
    bad["unit_of_measure"] = "L"
    with pytest.raises(PlanningError, match="units"):
        what(session, bad)
    resource = session.scalar(
        select(m.ProductionResource).where(m.ProductionResource.code == "SYN-MIX")
    )
    resource.monthly_hours = 0
    session.flush()
    line = what(session, demand(2500)).lines[0]
    assert (
        line.utilisation_pct is None and line.overload_hours == 5 and line.allocated_quantity == 0
    )
    load(session, tmp_path)
    run, _ = generate_forecasts(session, CUTOFF)
    order = m.SalesOrder(
        code="SYN-P6-FIRM",
        customer_id=1,
        order_date=date(2026, 10, 1),
        required_date=date(2026, 11, 1),
        status="confirmed",
    )
    session.add(order)
    session.flush()
    session.add(
        m.SalesOrderLine(
            sales_order_id=order.id, product_id=1, line_number=1, quantity=100, unit_price_gbp=1
        )
    )
    session.flush()
    with pytest.raises(PlanningError, match="double-count"):
        calculate(session, forecast_run_code=run.code)
    # Manual is explicitly additional demand; existing firm commitments remain protected.
    assert what(session, demand(2000)).lines[0].inventory_offset == 1900


def test_forecast_snapshot_reporting_api_preservation(production_session, tmp_path):
    session = production_session
    load(session, tmp_path)
    forecast, _ = generate_forecasts(session, CUTOFF)
    session.commit()
    before = snapshot(session)
    result, _ = calculate(session, forecast_run_code=forecast.code)
    assert len(result.lines) == 12 and len(result.capacity) == 6
    assert sum(r.inventory_offset for r in result.lines) == D("7359.000001")
    assert sum(r.net_requirement for r in result.lines) == D("1175.999999")
    assert sum(r.proposed_quantity for r in result.lines) == D("1175.999999")
    assert sum(r.allocated_quantity for r in result.lines) == D("331.999999")
    assert [r.product_id for r in result.lines if r.status != "FEASIBLE"] == [2]
    assert snapshot(session) == before
    saved, created = save_forecast_plan(session, forecast.code)
    assert created and save_forecast_plan(session, forecast.code) == (saved, False)
    assert len(list(session.scalars(select(m.ProductionPlanLine)))) == 12
    counts = {
        name: session.scalar(text(f"SELECT count(*) FROM {name}"))
        for name in (
            "vw_production_plan",
            "vw_capacity_utilisation",
            "vw_planning_constraints",
            "vw_forecast_to_production",
            "vw_planning_materials",
        )
    }
    assert list(counts.values()) == [12, 6, 1, 12, 8]
    assert len({(r.product_id, r.period_start) for r in result.lines}) == 12
    app = create_app()
    app.dependency_overrides[read_session] = lambda: session
    app.dependency_overrides[database_status] = lambda: "up"
    before = snapshot(session)
    with TestClient(app) as client:
        query = "?forecast_run_code=" + forecast.code
        response = client.get("/api/v1/planning/production-plan" + query)
        assert response.status_code == 200 and response.json()["total"] == 12
        assert (
            client.get("/api/v1/planning/production-plan" + query + "&product_id=2").json()["total"]
            == 3
        )
        assert (
            client.get(
                "/api/v1/planning/production-plan" + query + "&period_start=2026-12-01"
            ).json()["total"]
            == 4
        )
        assert client.get("/api/v1/planning/constraints" + query).json()["total"] == 1
        cap = client.get(
            "/api/v1/planning/capacity" + query + "&product_id=2&period_start=2026-12-01"
        ).json()
        assert cap["total"] == 1 and D(cap["items"][0]["required_hours"]) == D("11.76")
        assert (
            client.get("/api/v1/planning/production-plan" + query + "&limit=1&offset=12").json()[
                "items"
            ]
            == []
        )
        for extra in (
            "&unknown=x",
            "&limit=201",
            "&product_id=-1",
            "&period_start=2026-11-02",
            "&status=bad",
        ):
            assert client.get("/api/v1/planning/production-plan" + query + extra).status_code == 422
        assert client.get("/api/v1/planning/production-plan").status_code == 422
        assert (
            client.get("/api/v1/planning/production-plan?forecast_run_code=" + "0" * 64).status_code
            == 404
        )
        assert (
            client.get("/api/v1/planning/production-plan" + query + "&product_id=999").status_code
            == 404
        )
        response = client.post(
            "/api/v1/planning/production-plan/what-if", json={"demands": [demand(5000)]}
        )
        assert response.status_code == 200 and response.json()["persisted"] is False
        assert response.json()["lines"][0]["status"] == "CAPACITY_CONSTRAINED"
        assert (
            client.post(
                "/api/v1/planning/production-plan/what-if",
                json={"demands": [demand(10), demand(10)]},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/planning/production-plan/what-if", json={"demands": [demand(10, 999)]}
            ).status_code
            == 404
        )
        assert len(client.get("/openapi.json").json()["paths"]) == 31
        assert client.get("/docs").status_code == 200
    assert snapshot(session) == before
    # Changed input produces an immutable alternative snapshot; old runs are retained.
    policy = session.scalar(select(m.ProductionPolicy).where(m.ProductionPolicy.product_id == 1))
    policy.priority = 5
    session.flush()
    changed, created = save_forecast_plan(session, forecast.code)
    assert created and changed.code != saved.code
    policy.priority = 1
    session.flush()
    assert save_forecast_plan(session, forecast.code) == (saved, False)
    row = session.scalar(select(m.ProductionMaterialResult))
    row.required_quantity += 1
    session.flush()
    with pytest.raises(PlanningError, match="material reporting"):
        save_forecast_plan(session, forecast.code)


def test_phase6_migration(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Use --postgres for native migration preservation")
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
            command.upgrade(config, "0005_forecasting")
            with Session(connection, join_transaction_mode="create_savepoint") as session:
                seed_master_data(session)
                session.commit()
                before = {
                    name: connection.scalar(text(f"SELECT count(*) FROM {name}"))
                    for name in m.PHASE5_TABLES
                }
                command.upgrade(config, "head")
                assert not compare_metadata(MigrationContext.configure(connection), m.Base.metadata)
                assert len(inspect(connection).get_view_names(schema=schema)) == 20
                assert len(inspect(connection).get_table_names(schema=schema)) == 36
                assert seed_production_policies(session) == 6
                session.commit()
                command.downgrade(config, "0005_forecasting")
                assert {
                    name: connection.scalar(text(f"SELECT count(*) FROM {name}"))
                    for name in m.PHASE5_TABLES
                } == before
                command.upgrade(config, "head")
                assert not compare_metadata(MigrationContext.configure(connection), m.Base.metadata)
                forecast = m.ForecastRun(
                    code="0" * 64,
                    dataset_code="SYN-MIGRATION",
                    algorithm_version="test",
                    training_cutoff=date(2026, 9, 30),
                    horizon=3,
                    generated_at=datetime.now(UTC),
                    inputs={},
                    report={},
                )
                session.add(forecast)
                session.flush()
                session.add(
                    m.ProductionPlanRun(
                        code="1" * 64,
                        algorithm_version="test",
                        forecast_run_id=forecast.id,
                        generated_at=datetime.now(UTC),
                        inputs={},
                        report={},
                    )
                )
                session.commit()
                with pytest.raises(RuntimeError, match="Archive production"):
                    command.downgrade(config, "0005_forecasting")
        finally:
            transaction.rollback()


def test_missing_policy_bom_and_database_bounds(production_session):
    session = production_session
    policy = session.scalar(select(m.ProductionPolicy).where(m.ProductionPolicy.product_id == 1))
    savepoint = session.begin_nested()
    session.delete(policy)
    session.flush()
    with pytest.raises(PlanningError, match="Missing production policy"):
        what(session, demand(2500))
    savepoint.rollback()
    # A minimum greater than preferred is rejected by the database, not only the planner.
    with pytest.raises(IntegrityError), session.begin_nested():
        session.scalar(select(m.ProductionPolicy)).minimum_batch = D(5000)
        session.flush()
    bom = session.scalar(select(m.BillOfMaterial).where(m.BillOfMaterial.product_id == 1))
    bom.status = "retired"
    session.flush()
    with pytest.raises(PlanningError, match="active BOM"):
        what(session, demand(2500))


def test_receipts_reservations_and_material_rounding(production_session):
    session = production_session
    raw = session.scalar(select(m.Inventory).where(m.Inventory.raw_material_id == 1))
    raw.quantity = 100
    raw.reserved_quantity = 25
    order = m.PurchaseOrder(
        code="SYN-P6-INCOMING",
        supplier_id=1,
        order_date=date(2026, 10, 1),
        expected_date=date(2026, 11, 1),
        status="confirmed",
    )
    session.add(order)
    session.flush()
    session.add(
        m.PurchaseOrderLine(
            purchase_order_id=order.id,
            raw_material_id=1,
            line_number=1,
            quantity=100,
            unit_price_gbp=1,
        )
    )
    session.flush()
    line = what(session, demand(2800)).lines[0]
    material = next(r for r in line.materials if r.raw_material_id == 1)
    assert material.available_quantity == 175 and material.shortage_quantity == 25
    assert line.status == "MATERIAL_CONSTRAINED"
    order.status = "received"
    session.flush()
    assert what(session, demand(2800)).lines[0].materials[0].available_quantity == 75
