"""Preserve Phase 1-3 data, apply Phase 4, and verify real local HTTP and replay."""

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

from database.models import PHASE1_TABLES, Base, PlanningRun, ReorderRecommendation
from database.session import get_engine
from etl.load import scalar
from planning.inventory import SOURCE, generate, positions, recommendations, requirements


def historical_snapshot() -> dict:
    """Original 23 tables; exclude only explicitly identified Phase 4 proposal additions."""
    with Session(get_engine()) as session:
        tables = {}
        for name, table in Base.metadata.tables.items():
            if name not in PHASE1_TABLES:
                continue
            statement = select(table).order_by(table.c.id)
            if name == "reorder_recommendations":
                statement = statement.where(table.c.source_system != SOURCE)
            tables[name] = [
                {k: scalar(v) for k, v in row.items()}
                for row in session.execute(statement).mappings()
            ]
    return {
        "counts": {k: len(v) for k, v in tables.items()},
        "sha256": hashlib.sha256(json.dumps(tables, sort_keys=True).encode()).hexdigest(),
    }


def cli(*arguments: str) -> dict:
    output = subprocess.check_output(
        [sys.executable, "-m", "scripts.run_planning", *arguments], text=True
    )
    return json.loads(output)


def main() -> None:
    before = historical_snapshot()
    assert before["sha256"] == "2b71d22b48c0c0e1dcfe56226e3ba50590ec5b4389129064f9ba639d55b41ce9"
    subprocess.run([sys.executable, "-m", "scripts.migrate_db"], check=True)
    migrated = historical_snapshot()
    assert migrated == before
    policies = cli("seed-policies")
    assert cli("seed-policies")["inserted_policies"] == 0
    first_run, repeated = cli("calculate"), cli("calculate")
    assert first_run["run_code"] == repeated["run_code"] and repeated["created"] is False
    with Session(get_engine()) as session:
        stock = positions(session)
        needs = requirements(session)
        proposals = recommendations(session)
        assert needs == []
        assert len(stock) == 8
        assert [(p.raw_material_id, p.quantity) for p in proposals] == [(2, 1000), (3, 1500)]
        assert all(p.required_quantity == 0 for p in stock)
        view_counts = {
            name: session.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in inspect(session.connection()).get_view_names()
        }
        version = session.scalar(text("SHOW server_version"))
        revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        saved = session.scalar(select(PlanningRun).where(PlanningRun.code == first_run["run_code"]))
        assert saved is not None
        proposal_ids = list(session.scalars(select(ReorderRecommendation.id)))
        # Repeated service call also preserves the immutable run ID and result rows.
        assert generate(session)[0].id == saved.id
        input_snapshot = saved.inputs
    statuses = {}

    def request(path: str, expected: int = 200):
        try:
            with urlopen("http://127.0.0.1:18084" + path, timeout=5) as response:
                status, body = response.status, response.read()
        except HTTPError as error:
            status, body = error.code, error.read()
        assert status == expected, (path, status)
        statuses[path] = status
        return json.loads(body) if body.startswith(b"{") else None

    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_api"],
        env=dict(os.environ, API_HOST="127.0.0.1", API_PORT="18084"),
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
        specification = request("/openapi.json")
        assert len(specification["paths"]) == 23
        request("/api/v1/inventory/positions")
        request("/api/v1/inventory/positions?item_type=raw_material&item_id=2")
        request("/api/v1/planning/material-requirements")
        request("/api/v1/reorder-recommendations?status=proposed&warehouse_id=1")
        request("/api/v1/reorder-recommendations/" + str(proposal_ids[0]))
        what_if = request(
            "/api/v1/planning/material-availability?product_id=1&quantity=10000&unit_of_measure=kg"
        )
        assert len(what_if["materials"]) == 4
        assert all(Decimal(row["shortage_quantity"]) == 500 for row in what_if["materials"])
        assert what_if["persisted"] is False
        kpis = request("/api/v1/kpis/operations")
        phase3 = json.loads(Path("docs/evidence/phase3-live.json").read_text())
        assert kpis == phase3["kpis"]
        trace = request("/api/v1/traceability/order/1")
        assert trace == phase3["trace"]
        request("/api/v1/reorder-recommendations/999999", 404)
        request("/api/v1/inventory/positions?limit=201", 422)
        request(
            "/api/v1/planning/material-availability?product_id=1&quantity=1&unit_of_measure=L", 409
        )
    finally:
        process.terminate()
        process.wait(timeout=10)
    after = historical_snapshot()
    assert before == after
    with Session(get_engine()) as session:
        assert list(session.scalars(select(ReorderRecommendation.id))) == proposal_ids
        assert (
            session.scalar(
                select(PlanningRun).where(PlanningRun.code == first_run["run_code"])
            ).inputs
            == input_snapshot
        )
    evidence = dict(
        postgresql=version,
        migration=revision,
        historical_before=before,
        historical_after_migration=migrated,
        historical_after=after,
        unchanged=True,
        policies=policies,
        first_run=first_run,
        replay=repeated,
        health=health,
        http=statuses,
        view_counts=view_counts,
        positions=[p.model_dump(mode="json") for p in stock],
        requirements=[r.model_dump(mode="json") for r in needs],
        recommendations=[r.model_dump(mode="json") for r in proposals],
        what_if=what_if,
        phase3_kpis_and_trace_unchanged=True,
    )
    Path("docs/evidence/phase4-live.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: evidence[k]
                for k in (
                    "postgresql",
                    "migration",
                    "unchanged",
                    "policies",
                    "first_run",
                    "replay",
                    "view_counts",
                    "http",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
