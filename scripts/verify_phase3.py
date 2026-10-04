"""Explicit local Phase 3 migration and live HTTP verification; synthetic data only."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from analytics.queries import VIEW_NAMES
from database.models import Base
from database.session import get_engine
from etl.load import scalar
from etl.reconcile import business_snapshot


def snapshot():
    with Session(get_engine()) as session:
        rows = {
            name: [
                {key: scalar(value) for key, value in row.items()}
                for row in session.execute(select(table).order_by(table.c.id)).mappings()
            ]
            for name, table in Base.metadata.tables.items()
        }
        return {
            "business": business_snapshot(session),
            "all_table_counts": {name: len(values) for name, values in rows.items()},
            "all_tables_sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode()
            ).hexdigest(),
        }


def main():
    before = snapshot()
    subprocess.run([sys.executable, "-m", "scripts.migrate_db"], check=True)
    with get_engine().connect() as connection:
        version = connection.scalar(text("SHOW server_version"))
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert set(VIEW_NAMES).issubset(inspect(connection).get_view_names())
        view_counts = {
            name: connection.scalar(text(f"SELECT count(*) FROM {name}")) for name in VIEW_NAMES
        }
    statuses = {}

    def request(path, expected=200, method="GET"):
        try:
            with urlopen(
                Request("http://127.0.0.1:18083" + path, method=method), timeout=5
            ) as response:
                status, content = response.status, response.read()
        except HTTPError as error:
            status, content = error.code, error.read()
        assert status == expected, (path, status)
        statuses[method + " " + path] = status
        return json.loads(content) if content.startswith(b"{") else None

    environment = dict(os.environ, API_HOST="127.0.0.1", API_PORT="18083")
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_api"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("API process exited before readiness")
            try:
                health = request("/health")
                break
            except URLError:
                time.sleep(0.25)
        else:
            raise RuntimeError("API readiness timed out")
        request("/docs")
        specification = request("/openapi.json")
        resources = [
            "products",
            "raw-materials",
            "suppliers",
            "customers",
            "inventory",
            "sales-orders",
            "purchase-orders",
            "production-orders",
            "production-batches",
            "quality-inspections",
            "shipments",
            "etl-runs",
            "data-quality-issues",
        ]
        totals = {
            resource: request("/api/v1/" + resource + "?limit=2&offset=0")["total"]
            for resource in resources
        }
        request("/api/v1/inventory/1")
        request("/api/v1/sales-orders/1")
        trace = request("/api/v1/traceability/order/1")
        assert trace["code"] == "SO-0001"
        assert len(trace["lines"][0]["production_orders"][0]["batches"][0]["materials"]) == 4
        kpis = request("/api/v1/kpis/operations")
        assert kpis["order_count"] == 48
        assert kpis["etl_rows_extracted"] == 928
        request("/api/v1/products?active=true&limit=1&offset=1")
        request("/api/v1/sales-orders/999999", 404)
        request("/api/v1/products?limit=201", 422)
        request("/api/v1/products", 405, "POST")
    finally:
        process.terminate()
        process.wait(timeout=10)
    after = snapshot()
    assert before == after, "Operational or audit data changed"
    assert before["business"]["sha256"] == (
        "1a99a4e86ed0b968a9e1bd20626014e1f0c7182c42146d19e2d68f95f9ba9883"
    )
    evidence = {
        "postgresql": version,
        "migration": revision,
        "before": before,
        "after": after,
        "unchanged": before == after,
        "view_counts": view_counts,
        "http": statuses,
        "health": health,
        "openapi_path_count": len(specification["paths"]),
        "list_totals": totals,
        "trace": trace,
        "kpis": kpis,
    }
    Path("docs/evidence/phase3-live.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: evidence[key]
                for key in (
                    "postgresql",
                    "migration",
                    "unchanged",
                    "view_counts",
                    "http",
                    "list_totals",
                    "kpis",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
