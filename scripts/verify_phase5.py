"""Explicit native PostgreSQL forecast workflow, replay and preservation evidence."""

import hashlib
import json
import os
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from database import models as m
from database.session import get_engine
from etl.load import scalar
from planning.forecast_models import metrics
from planning.forecasting import SOURCE
from planning.inventory import generate as generate_reorders


def prior_snapshot() -> dict:
    with get_engine().connect() as connection:
        rows = {}
        for name, table in m.Base.metadata.tables.items():
            if name not in m.PHASE4_TABLES:
                continue
            statement = select(table).order_by(table.c.id)
            if name == "demand_forecasts":
                statement = statement.where(table.c.source_system != SOURCE)
            rows[name] = [
                {k: scalar(v) for k, v in row.items()}
                for row in connection.execute(statement).mappings()
            ]
    return dict(
        counts={k: len(v) for k, v in rows.items()},
        sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
    )


def cli(*args: str) -> dict:
    return json.loads(
        subprocess.check_output([sys.executable, "-m", "scripts.run_forecasting", *args], text=True)
    )


def main() -> None:
    baseline = json.loads(Path("docs/evidence/phase5-before.json").read_text())
    before = prior_snapshot()
    assert before["sha256"] == baseline["sha256"] and before["counts"] == baseline["counts"]
    subprocess.run([sys.executable, "-m", "scripts.migrate_db"], check=True)
    assert prior_snapshot() == before
    manifest = cli("generate-history")
    assert cli("generate-history") == manifest
    imported = cli("ingest-history")
    assert cli("ingest-history")["inserted_observations"] == 0
    first = cli("forecast")
    replay = cli("forecast")
    assert first["run_code"] == replay["run_code"] and replay["created"] is False
    assert first["generated_at"] == replay["generated_at"]
    assert first["forecasts"] == replay["forecasts"] and first["metrics"] == replay["metrics"]
    demo = cli("demo-bom", "--run-code", first["run_code"], "--product-id", "1")
    assert all(
        Decimal(r["incremental_requirement"])
        == (Decimal(demo["forecast_quantity"]) / 4).quantize(Decimal("0.000001"))
        for r in demo["result"]["materials"]
    )
    with Session(get_engine()) as session:
        version = session.scalar(text("SHOW server_version"))
        revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        views = {
            name: session.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in inspect(session.connection()).get_view_names()
        }
        assert (
            views["vw_demand_history"] == 96
            and views["vw_demand_forecast"] == 12
            and views["vw_forecast_accuracy"] == 30
        )
        assert session.scalar(select(text("count(*)")).select_from(m.ForecastRun)) == 1
        assert session.scalar(select(text("count(*)")).select_from(m.DemandObservation)) == 192
        # Confirm forecasting did not alter Phase 4 numerical inputs or create purchasing proposals.
        reorder, created = generate_reorders(session)
        phase4 = json.loads(Path("docs/evidence/phase4-live.json").read_text())
        assert created is False and reorder.code == phase4["first_run"]["run_code"]
    statuses = {}

    def request(path: str, expected: int = 200):
        try:
            with urlopen("http://127.0.0.1:18085" + path, timeout=5) as response:
                status, body = response.status, response.read()
        except HTTPError as error:
            status, body = error.code, error.read()
        assert status == expected, (path, status)
        statuses[path] = status
        return json.loads(body) if body.startswith(b"{") else None

    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_api"],
        env=dict(os.environ, API_HOST="127.0.0.1", API_PORT="18085"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("API exited before readiness")
            try:
                health = request("/health")
                break
            except URLError:
                time.sleep(0.25)
        else:
            raise RuntimeError("API readiness timed out")
        request("/docs")
        assert len(request("/openapi.json")["paths"]) == 27
        forecast_response = request("/api/v1/forecasts?run_code=" + first["run_code"])
        assert forecast_response["total"] == 12
        assert request("/api/v1/forecasts/1")["total"] == 3
        assert request("/api/v1/forecasts?date_from=2026-11-01&date_to=2026-11-01")["total"] == 4
        assert request("/api/v1/forecasts/history?product_id=1")["total"] == 24
        evaluation = request("/api/v1/forecasts/evaluation?scope=overall&evaluation_split=test")
        assert evaluation["total"] == 3
        request("/api/v1/forecasts/999999", 404)
        request("/api/v1/forecasts?limit=201", 422)
        phase3 = json.loads(Path("docs/evidence/phase3-live.json").read_text())
        assert request("/api/v1/kpis/operations") == phase3["kpis"]
        assert request("/api/v1/traceability/order/1") == phase3["trace"]
        inventory = request("/api/v1/inventory/positions")["items"]
        assert inventory == phase4["positions"]
        assert request("/api/v1/reorder-recommendations")["total"] == 2
    finally:
        process.terminate()
        process.wait(timeout=10)
    after = prior_snapshot()
    assert after == before
    selected_metrics = {}
    for split in ("validation", "test"):
        points = [
            p
            for p in first["points"]
            if p["split"] == split and p["model"] == first["selected_models"][str(p["product_id"])]
        ]
        selected_metrics[split] = {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in metrics(
                [Decimal(p["actual"]) for p in points],
                [Decimal(p["predicted"]) for p in points],
            ).items()
        }
    evidence = dict(
        postgresql=version,
        migration=revision,
        before=before,
        after=after,
        unchanged=True,
        sales_assessment=baseline["sales_assessment"],
        manifest=manifest,
        imported=imported,
        first=first,
        replay=dict(
            run_code=replay["run_code"],
            created=replay["created"],
            generated_at=replay["generated_at"],
        ),
        bom_demo=demo,
        views=views,
        health=health,
        http=statuses,
        forecasts_http=forecast_response,
        evaluation_http=evaluation,
        phase3_and_phase4_unchanged=True,
        selected_policy_metrics=selected_metrics,
    )
    Path("docs/evidence/phase5-live.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                postgresql=version,
                migration=revision,
                unchanged=True,
                imported=imported,
                run_code=first["run_code"],
                replay_created=replay["created"],
                selected_models=first["selected_models"],
                forecasts=first["forecasts"],
                overall_metrics=[r for r in first["metrics"] if r["product_id"] is None],
                bom_quantity=demo["forecast_quantity"],
                views=views,
                http=statuses,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
