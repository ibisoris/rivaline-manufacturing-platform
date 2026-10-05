"""Explicit native Phase 6 migration, scenarios, HTTP and preservation evidence."""

import hashlib
import json
import os
import subprocess
import sys
import time
from decimal import Decimal as D
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from database import models as m
from database.seed import seed_master_data
from database.session import get_engine
from etl.load import scalar
from planning.production import calculate, seed_production_policies
from planning.production_contracts import WhatIf


def prior_snapshot() -> dict:
    with get_engine().connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        rows = {
            name: [
                {k: scalar(v) for k, v in r.items()}
                for r in connection.execute(select(t).order_by(t.c.id)).mappings()
            ]
            for name, t in m.Base.metadata.tables.items()
            if name in m.PHASE5_TABLES
        }
    return dict(
        counts={k: len(v) for k, v in rows.items()},
        sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
    )


def cli(*args: str) -> dict:
    return json.loads(
        subprocess.check_output([sys.executable, "-m", "scripts.run_production", *args], text=True)
    )


def evaluation() -> dict:
    """Scenario inputs live only in a new schema inside a rolled-back transaction."""
    evidence = {}
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            schema = "phase1_test_" + uuid4().hex
            connection.execute(CreateSchema(schema))
            connection.execute(
                text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
            )
            connection = connection.execution_options(schema_translate_map={None: schema})
            m.Base.metadata.create_all(connection)
            with Session(connection, join_transaction_mode="create_savepoint") as session:
                for name in (
                    "0002_reporting.sql",
                    "0003_planning.sql",
                    "0005_forecasting.sql",
                    "0006_production.sql",
                ):
                    for sql in Path("database/migrations/versions", name).read_text().split(";"):
                        if sql.strip():
                            session.execute(text(sql))
                session.execute(
                    text(
                        Path("database/migrations/versions/0004_fractional_bom.sql")
                        .read_text()
                        .replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1)
                    )
                )
                seed_master_data(session)
                seed_production_policies(session)
                for index in range(1, 5):
                    for field in ("product_id", "raw_material_id"):
                        session.add(
                            m.Inventory(
                                **{field: index},
                                warehouse_id=1,
                                lot_code="SYN-P6-EVAL",
                                quantity=2000,
                                reserved_quantity=0,
                            )
                        )
                session.flush()
                cases = [
                    ("stock_covered", 1000, 2000, 10, "FEASIBLE"),
                    ("production_feasible", 2500, 2000, 10, "FEASIBLE"),
                    ("material_only", 3000, 100, 10, "MATERIAL_CONSTRAINED"),
                    ("capacity_only", 3500, 2000, 10, "CAPACITY_CONSTRAINED"),
                    ("combined", 3500, 100, 10, "MATERIAL_AND_CAPACITY_CONSTRAINED"),
                    ("partial_batch", 4300, 2000, 30, "FEASIBLE"),
                    ("minimum_adjustment", 4100, 2000, 30, "FEASIBLE"),
                    ("what_if_new_constraint", 5000, 2000, 10, "CAPACITY_CONSTRAINED"),
                ]
                for label, quantity, stock, available, status in cases:
                    for row in session.scalars(
                        select(m.Inventory).where(m.Inventory.raw_material_id.is_not(None))
                    ):
                        row.quantity = D(stock)
                    session.scalar(
                        select(m.ProductionResource).where(m.ProductionResource.code == "SYN-MIX")
                    ).monthly_hours = D(available)
                    session.flush()
                    request = WhatIf(
                        demands=[
                            dict(
                                product_id=1,
                                period_start="2026-11-01",
                                quantity=quantity,
                                unit_of_measure="kg",
                            )
                        ]
                    )
                    result, _ = calculate(session, request=request)
                    assert result.lines[0].status == status
                    evidence[label] = result.model_dump(mode="json")
                request = WhatIf(
                    demands=[
                        dict(
                            product_id=i,
                            period_start="2026-11-01",
                            quantity=2800,
                            unit_of_measure="kg",
                        )
                        for i in (2, 1)
                    ]
                )
                result, _ = calculate(session, request=request)
                assert [r.allocated_quantity for r in result.lines] == [D(800), D(0)]
                evidence["competing_products"] = result.model_dump(mode="json")
        finally:
            transaction.rollback()
    return evidence


def planning_kpis(report: dict) -> dict:
    """Benchmark measures at explicit grains; this live fixture is entirely kg."""
    lines, capacity = report["lines"], report["capacity"]
    assert {line["unit_of_measure"] for line in lines} == {"kg"}
    fields = (
        "gross_demand",
        "inventory_offset",
        "surplus_offset",
        "net_requirement",
        "proposed_quantity",
        "allocated_quantity",
        "unmet_quantity",
    )
    result = {key: str(sum((D(line[key]) for line in lines), D(0))) for key in fields}
    feasible = sum(line["status"] == "FEASIBLE" for line in lines)
    constrained = {line["product_id"] for line in lines if line["status"] != "FEASIBLE"}
    result.update(
        unit_of_measure="kg",
        proposed_batches=sum(line["batch_count"] for line in lines),
        product_months=len(lines),
        feasible_product_months=feasible,
        feasible_plan_percentage=str((D(feasible) * 100 / len(lines)).quantize(D(".01"))),
        constrained_product_count=len(constrained),
        feasible_product_count=len({line["product_id"] for line in lines} - constrained),
    )
    result["capacity"] = {
        key: str(sum((D(row[key]) for row in capacity), D(0)))
        for key in ("required_hours", "available_hours", "allocated_hours", "overload_hours")
    }
    result["capacity"]["horizon_utilisation_pct"] = str(
        (
            D(result["capacity"]["required_hours"]) * 100 / D(result["capacity"]["available_hours"])
        ).quantize(D(".01"))
    )
    materials = {}
    for line in lines:
        for row in line["materials"]:
            dest = materials.setdefault(
                row["material_code"],
                dict(
                    unit_of_measure=row["unit_of_measure"],
                    required_quantity=D(0),
                    shortage_quantity=D(0),
                    allocated_quantity=D(0),
                ),
            )
            for key in ("required_quantity", "shortage_quantity", "allocated_quantity"):
                dest[key] += D(row[key])
    result["materials"] = {
        code: {key: str(value) if isinstance(value, D) else value for key, value in values.items()}
        for code, values in materials.items()
    }
    return result


def main() -> None:
    baseline = json.loads(Path("docs/evidence/phase6-before.json").read_text())
    before = prior_snapshot()
    assert before == baseline
    subprocess.run([sys.executable, "-m", "scripts.migrate_db"], check=True)
    assert prior_snapshot() == before
    seeded = cli("seed-policies")
    assert cli("seed-policies") == {"inserted": 0}
    with Session(get_engine()) as session:
        codes = list(session.scalars(select(m.ForecastRun.code)))
        assert len(codes) == 1, "Select the verified Phase 5 forecast vintage explicitly"
        forecast_code = codes[0]
        version = session.scalar(text("SHOW server_version"))
    calculated = cli("forecast", "--forecast-run-code", forecast_code)
    first = cli("save-forecast", "--forecast-run-code", forecast_code)
    replay = cli("save-forecast", "--forecast-run-code", forecast_code)
    assert replay["created"] is False and first["plan_run_code"] == replay["plan_run_code"]
    assert first["generated_at"] == replay["generated_at"]
    assert first["report"] == calculated == replay["report"]
    demo = cli(
        "what-if",
        "--product-id",
        "1",
        "--period",
        "2026-11-01",
        "--quantity",
        "5000",
        "--unit",
        "kg",
    )
    assert demo["persisted"] is False
    assert demo["lines"][0]["status"] == "CAPACITY_CONSTRAINED"
    assert prior_snapshot() == before
    scenarios = evaluation()
    statuses = {}

    def request(path: str, expected: int = 200, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(
            "http://127.0.0.1:18086" + path,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urlopen(req, timeout=15) as response:
                status, body = response.status, response.read()
        except HTTPError as error:
            status, body = error.code, error.read()
        assert status == expected, (path, status)
        statuses[("POST " if data else "GET ") + path] = status
        return json.loads(body) if body.startswith(b"{") else None

    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_api"],
        env=dict(os.environ, API_HOST="127.0.0.1", API_PORT="18086"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("API exited before readiness")
            try:
                request("/health")
                break
            except URLError:
                time.sleep(0.25)
        else:
            raise RuntimeError("API readiness timed out")
        request("/docs")
        assert len(request("/openapi.json")["paths"]) == 31
        query = "?forecast_run_code=" + forecast_code
        plan = request("/api/v1/planning/production-plan" + query)
        assert plan["total"] == 12 and plan["items"] == calculated["lines"]
        assert request("/api/v1/planning/capacity" + query)["total"] == 6
        assert request("/api/v1/planning/constraints" + query)["total"] == 1
        assert (
            request(
                "/api/v1/planning/production-plan" + query + "&product_id=2&period_start=2026-12-01"
            )["total"]
            == 1
        )
        request("/api/v1/planning/production-plan" + query + "&limit=201", 422)
        request("/api/v1/planning/production-plan?forecast_run_code=" + "0" * 64, 404)
        http_demo = request(
            "/api/v1/planning/production-plan/what-if",
            payload={
                "demands": [
                    dict(
                        product_id=1,
                        period_start="2026-11-01",
                        quantity="5000",
                        unit_of_measure="kg",
                    )
                ]
            },
        )
        assert http_demo == demo
        old = json.loads(Path("docs/evidence/phase3-live.json").read_text())
        assert request("/api/v1/kpis/operations") == old["kpis"]
        assert request("/api/v1/traceability/order/1") == old["trace"]
        phase4 = json.loads(Path("docs/evidence/phase4-live.json").read_text())
        assert request("/api/v1/inventory/positions")["items"] == phase4["positions"]
        assert request("/api/v1/reorder-recommendations")["total"] == 2
        assert request("/api/v1/forecasts?run_code=" + forecast_code)["total"] == 12
        assert request("/api/v1/forecasts/evaluation")["total"] == 30
    finally:
        process.terminate()
        process.wait(timeout=10)
    with Session(get_engine()) as session:
        views = {
            name: session.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in inspect(session.connection()).get_view_names()
        }
        counts = {
            name: session.scalar(select(text("count(*)")).select_from(t))
            for name, t in m.Base.metadata.tables.items()
        }
        assert [
            views[n]
            for n in (
                "vw_production_plan",
                "vw_capacity_utilisation",
                "vw_planning_constraints",
                "vw_forecast_to_production",
                "vw_planning_materials",
            )
        ] == [12, 6, 1, 12, 8]
        revision = session.scalar(text("SELECT version_num FROM alembic_version"))
    after = prior_snapshot()
    assert before == after
    evidence = dict(
        server_version=version,
        revision=revision,
        before=before,
        after=after,
        seeded=seeded,
        first_run=first,
        replay_created=replay["created"],
        what_if=demo,
        evaluation_scenarios=scenarios,
        view_counts=views,
        counts=counts,
        http_statuses=statuses,
        planning_kpis=planning_kpis(calculated),
    )
    Path("docs/evidence/phase6-live.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                preserved=True,
                rows=sum(counts.values()),
                plan_run_code=first["plan_run_code"],
                prior_sha256=before["sha256"],
                http_checks=len(statuses),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
