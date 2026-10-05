"""Forecast correctness, time separation, archive lineage and PostgreSQL preservation."""

import csv
import hashlib
import json
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
from sqlalchemy import MetaData, func, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema
from test_api_analytics import reporting_session  # noqa: F401
from test_planning import planning_session  # noqa: F401

from api.dependencies import read_session
from api.main import create_app
from api.services.health import database_status
from database import models as m
from database.seed import seed_master_data
from database.session import get_engine
from etl.demand_history import DATASET, START, generate_history, ingest_history
from etl.reconcile import business_snapshot
from planning.forecast_models import (
    MODELS,
    ForecastError,
    evaluate,
    metrics,
    month_add,
    predict,
    select_model,
)
from planning.forecasting import forecast_to_bom, generate_forecasts, history

CUTOFF = date(2026, 9, 30)


@pytest.fixture
def forecast_session(planning_session):  # noqa: F811
    session = planning_session
    for sql in (
        Path("database/migrations/versions/0005_forecasting.sql")
        .read_text(encoding="utf-8-sig")
        .split(";")
    ):
        if sql.strip():
            session.execute(text(sql))
    session.commit()
    return session


def load(session, path):
    generate_history(path)
    assert ingest_history(session, path) == 192
    session.flush()


def test_deterministic_archive(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    assert generate_history(first) == generate_history(second)
    for name in ("demand_history.csv", "manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    rows = list(csv.DictReader((first / "demand_history.csv").open()))
    assert len(rows) == 192 and len({r["record_id"] for r in rows}) == 192
    assert min(r["period_start"] for r in rows) == "2024-10-01"
    assert max(r["period_start"] for r in rows) == "2026-09-01"
    assert {r["unit_of_measure"] for r in rows} == {"kg"}


@pytest.mark.parametrize(
    "model,expected",
    [("naive", [5, 5, 5]), ("moving_average", [3, 3, 3]), ("linear_trend", [7, 9, 11])],
)
def test_model_predictions(model, expected):
    assert predict(list(map(D, (1, 3, 5))), model) == list(map(D, expected))
    assert predict([D(0)] * 12, model) == [D(0)] * 3
    assert all(q >= 0 for q in predict(list(map(D, (3, 2, 1))), model))


def test_metrics_and_selection():
    assert metrics([D(0), D(10)], [D(2), D(8)]) == dict(
        observations=2, mae=D(2), rmse=D(2), wape_pct=D(40)
    )
    assert metrics([D(0), D(4)], [D(0), D(0)])["rmse"] == D("2.828427")
    assert metrics([D(0)], [D(2)])["wape_pct"] is None
    assert select_model({name: {"mae": D(1)} for name in MODELS}) == "naive"
    assert (
        select_model(
            {"naive": {"mae": D(3)}, "moving_average": {"mae": D(1)}, "linear_trend": {"mae": D(2)}}
        )
        == "moving_average"
    )
    with pytest.raises(ForecastError):
        metrics([], [])


def test_chronology_and_holdout_no_leakage():
    periods = [month_add(START, i) for i in range(24)]
    values = [D(100 + 2 * i) for i in range(24)]
    result = evaluate(values, periods)
    changed = evaluate(values[:21] + [D(999999)] * 3, periods)
    assert result["selected_model"] == changed["selected_model"] == "linear_trend"
    assert result["metrics"]["validation"] == changed["metrics"]["validation"]
    assert [p for p in result["points"] if p["split"] == "validation"] == [
        p for p in changed["points"] if p["split"] == "validation"
    ]
    assert [p["predicted"] for p in result["points"] if p["split"] == "test"] == [
        p["predicted"] for p in changed["points"] if p["split"] == "test"
    ]
    assert result["metrics"]["test"] != changed["metrics"]["test"]
    assert all(p["training_cutoff"] < p["period_start"] for p in result["points"])
    assert len(result["points"]) == 36
    with pytest.raises(ForecastError, match="Missing"):
        evaluate(values, periods[:10] + [month_add(periods[10], 1)] + periods[11:])


def test_archive_aggregation_replay_and_missing(forecast_session, tmp_path):
    session = forecast_session
    before = business_snapshot(session)
    load(session, tmp_path)
    assert ingest_history(session, tmp_path) == 0
    assert business_snapshot(session) == before
    sources, series = history(session, DATASET, CUTOFF)
    assert len(sources) == 192 and all(len(r) == 24 for r in series.values())
    raw = list(csv.DictReader((tmp_path / "demand_history.csv").open()))
    expected = sum(
        D(r["quantity"])
        for r in raw
        if r["product_code"] == "SYN-FG-001" and r["period_start"] == "2024-10-01"
    )
    assert series[1][0]["quantity"] == expected
    rows = session.execute(text("SELECT * FROM vw_demand_history")).mappings().all()
    assert len(rows) == 96 and all(r["source_rows"] == 2 for r in rows)
    # Removing both source fragments of a month must fail rather than becoming zero.
    missing = list(
        session.scalars(
            select(m.DemandObservation).where(
                m.DemandObservation.product_id == 1, m.DemandObservation.period_start == START
            )
        )
    )
    for row in missing:
        session.delete(row)
    session.flush()
    with pytest.raises(ForecastError, match="contiguous"):
        generate_forecasts(session, CUTOFF)


@pytest.mark.parametrize("defect", ["unit", "duplicate", "quantity", "period"])
def test_invalid_archive_rejected_atomically(forecast_session, tmp_path, defect):
    generate_history(tmp_path)
    path = tmp_path / "demand_history.csv"
    with path.open() as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    if defect == "unit":
        rows[0]["unit_of_measure"] = "L"
    elif defect == "duplicate":
        rows[0]["record_id"] = rows[1]["record_id"]
    elif defect == "quantity":
        rows[0]["quantity"] = ""
    else:
        rows[0]["period_start"] = "2024-10-02"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ForecastError):
        ingest_history(forecast_session, tmp_path)
    assert forecast_session.scalar(select(func.count()).select_from(m.DemandObservation)) == 0


def test_forecast_persistence_api_and_bom(forecast_session, tmp_path):
    session = forecast_session
    load(session, tmp_path)
    run, created = generate_forecasts(session, CUTOFF)
    assert created
    session.commit()
    assert generate_forecasts(session, CUTOFF) == (run, False)
    assert session.scalar(select(func.count()).select_from(m.DemandForecast)) == 12
    assert session.scalar(select(func.count()).select_from(m.ForecastMetric)) == 30
    assert len(run.report["points"]) == 144
    assert session.scalar(text("SELECT count(*) FROM vw_forecast_backtest")) == 144
    assert session.scalar(select(func.count()).select_from(m.ForecastBacktest)) == 144
    before = business_snapshot(session)
    demo = forecast_to_bom(session, run.code, 1)
    total = sum(D(f["quantity"]) for f in run.report["forecasts"] if f["product_id"] == 1)
    assert all(
        D(r["incremental_requirement"]) == (total / D(4)).quantize(D("0.000001"))
        for r in demo["result"]["materials"]
    )
    assert demo["persisted"] is False and business_snapshot(session) == before
    app = create_app()
    app.dependency_overrides[read_session] = lambda: session
    app.dependency_overrides[database_status] = lambda: "up"
    with TestClient(app) as client:
        response = client.get("/api/v1/forecasts")
        assert response.status_code == 200 and response.json()["total"] == 12
        assert {r["product_id"] for r in response.json()["items"]} == {1, 2, 3, 4}
        assert all(D(r["quantity"]) >= 0 for r in response.json()["items"])
        assert all(r["generated_at"].endswith("Z") for r in response.json()["items"])
        assert client.get("/api/v1/forecasts/1").json()["total"] == 3
        assert client.get("/api/v1/forecasts/999").status_code == 404
        assert (
            client.get("/api/v1/forecasts?date_from=2026-11-01&date_to=2026-11-01").json()["total"]
            == 4
        )
        assert client.get("/api/v1/forecasts?limit=2&offset=12").json()["items"] == []
        assert client.get("/api/v1/forecasts?model_version=unknown").json()["total"] == 0
        accuracy = client.get(
            "/api/v1/forecasts/evaluation?scope=overall&evaluation_split=test"
        ).json()
        assert accuracy["total"] == 3 and {r["model_name"] for r in accuracy["items"]} == set(
            MODELS
        )
        assert (
            client.get("/api/v1/forecasts/evaluation?product_id=1&model_name=naive").json()["total"]
            == 2
        )
        assert client.get("/api/v1/forecasts/history?product_id=1").json()["total"] == 24
        for query in (
            "?limit=201",
            "?product_id=-1",
            "?unknown=x",
            "?date_from=2026-12-01&date_to=2026-11-01",
        ):
            assert client.get("/api/v1/forecasts" + query).status_code == 422
        assert client.post("/api/v1/forecasts").status_code == 405
        assert len(client.get("/openapi.json").json()["paths"]) == 31
    assert business_snapshot(session) == before
    # Appending a future observation cannot alter a run at the fixed earlier cutoff.
    session.add(
        m.DemandObservation(
            dataset_code=DATASET,
            product_id=1,
            period_start=date(2026, 10, 1),
            quantity=99999,
            unit_of_measure="kg",
            file_sha256="0" * 64,
            source_system="test_future",
            source_record_id="future",
        )
    )
    session.flush()
    assert generate_forecasts(session, CUTOFF) == (run, False)
    # A changed saved prediction is a conflict, not silent repair or a duplicate run.
    session.scalar(select(m.DemandForecast)).quantity += 1
    session.flush()
    with pytest.raises(ForecastError, match="conflicts"):
        generate_forecasts(session, CUTOFF)


def test_phase5_migration(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Use --postgres for forecasting migration preservation checks")
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
            command.upgrade(config, "0004_fractional_bom")
            with Session(connection, join_transaction_mode="create_savepoint") as session:
                seed_master_data(session)
                session.commit()
                before = business_snapshot(session)
                command.upgrade(config, "0005_forecasting")
                assert business_snapshot(session) == before
                assert len(inspect(connection).get_view_names(schema=schema)) == 15
                baseline = MetaData(naming_convention=m.Base.metadata.naming_convention)
                for name in m.PHASE5_TABLES:
                    m.Base.metadata.tables[name].to_metadata(baseline)
                assert not compare_metadata(MigrationContext.configure(connection), baseline)
                command.downgrade(config, "0004_fractional_bom")
                assert business_snapshot(session) == before
                command.upgrade(config, "0005_forecasting")
                assert len(inspect(connection).get_table_names(schema=schema)) == 30
        finally:
            transaction.rollback()


def test_changed_input_keeps_old_forecast_and_archive_conflicts(forecast_session, tmp_path):
    session = forecast_session
    load(session, tmp_path)
    run, _ = generate_forecasts(session, CUTOFF)
    original = json.dumps(run.report, sort_keys=True)
    row = session.scalar(select(m.DemandObservation))
    row.quantity += D(1)
    session.flush()
    with pytest.raises(ForecastError, match="replay conflict"):
        ingest_history(session, tmp_path)
    changed, created = generate_forecasts(session, CUTOFF)
    assert created and changed.code != run.code
    assert json.dumps(run.report, sort_keys=True) == original
    assert session.scalar(select(func.count()).select_from(m.DemandForecast)) == 24
    row.quantity -= D(1)
    session.flush()
    assert generate_forecasts(session, CUTOFF) == (run, False)
    assert ingest_history(session, tmp_path) == 0
