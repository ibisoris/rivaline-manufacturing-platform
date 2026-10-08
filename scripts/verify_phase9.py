"""Preserved-demo verification: read-only DB/API, isolated fixture generation, local evidence."""

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from database import models as m
from database.session import get_engine
from etl.contracts import SOURCES
from etl.extract import extract
from etl.fixtures import generate
from etl.reconcile import reconcile as reconcile_etl
from scripts.validate_powerbi import validate
from scripts.verify_phase7 import import_rows, reconcile, snapshot

EVIDENCE = Path("docs/evidence/phase9-live.json")


def database_evidence() -> dict:
    with get_engine().connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        with Session(conn, autoflush=False) as session:
            current = snapshot(session)
            baseline = json.loads(Path("docs/evidence/phase7-before.json").read_text())
            assert current == baseline, "Preserved demonstration database differs from baseline"
            runs = list(session.scalars(select(m.EtlRun).order_by(m.EtlRun.id)))
            reconciliations = []
            for run in runs:
                summary = Path("data/quarantine") / run.code / "summary.json"
                result = reconcile_etl(session, summary, Path("data/legacy"))
                assert result["ok"], result["failures"]
                saved = json.loads(summary.read_text())
                result["inserted_targets"] = saved["inserted_targets"]
                reconciliations.append(result)
            assert [r["inserted_targets"] for r in reconciliations] == [944, 0]
            sample = session.scalar(select(m.DataQualityIssue).order_by(m.DataQualityIssue.id))
            return dict(
                snapshot=current,
                server=conn.scalar(text("SHOW server_version")),
                migration=conn.scalar(text("SELECT version_num FROM alembic_version")),
                reporting_views=len(inspect(conn).get_view_names(schema="public")),
                etl=reconciliations,
                rejected_example=dict(
                    rule=sample.rule_code,
                    message=sample.message,
                    source=sample.details["source"],
                    raw=sample.details["raw"],
                ),
                reporting=reconcile(import_rows(session)),
            )


def http_evidence() -> dict:
    # Reserve an available loopback port, then launch only our own temporary API process.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, API_HOST="127.0.0.1", API_PORT=str(port))
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_api"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **options,
    )
    base = f"http://127.0.0.1:{port}"

    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(req, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            body = json.loads(raw) if "json" in response.headers.get("Content-Type", "") else None
            return {"status": response.status, "body": body}

    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("Temporary API process exited before readiness")
            try:
                health = request("/health")
                if health["status"] == 200:
                    break
            except (URLError, TimeoutError):
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Temporary API did not become healthy")
        results = {"/health": health}
        for path in [
            "/docs",
            "/openapi.json",
            "/api/v1/sales-orders?limit=5",
            "/api/v1/kpis/operations",
            "/api/v1/inventory/positions",
            "/api/v1/reorder-recommendations?status=proposed",
            "/api/v1/forecasts",
            "/api/v1/forecasts/evaluation?scope=overall&evaluation_split=test",
            "/api/v1/etl-runs",
            "/api/v1/data-quality-issues?limit=5",
        ]:
            results[path] = request(path)
            assert results[path]["status"] == 200, path
        order = results["/api/v1/sales-orders?limit=5"]["body"]["items"][0]
        trace_path = f"/api/v1/traceability/order/{order['id']}"
        results[trace_path] = request(trace_path)
        assert results[trace_path]["status"] == 200
        assert results[trace_path]["body"]["lines"]
        forecast = results["/api/v1/forecasts"]["body"]["items"][0]
        code = forecast["run_code"]
        for route in ["production-plan", "capacity", "constraints"]:
            path = f"/api/v1/planning/{route}?forecast_run_code={code}"
            results[path] = request(path)
            assert results[path]["status"] == 200, path
        what_if = "/api/v1/planning/production-plan/what-if"
        results[what_if] = request(
            what_if,
            {
                "demands": [
                    {
                        "product_id": forecast["product_id"],
                        "period_start": "2026-11-01",
                        "quantity": "5000",
                        "unit_of_measure": "kg",
                    }
                ]
            },
        )
        assert results[what_if]["status"] == 200
        bad = "/api/v1/sales-orders?limit=0"
        results[bad] = request(bad)
        assert results[bad]["status"] == 422
        missing = "/api/v1/traceability/order/999999"
        results[missing] = request(missing)
        assert results[missing]["status"] == 404
        kpis = results["/api/v1/kpis/operations"]["body"]
        assert kpis["order_count"] == 48 and kpis["data_quality_issue_count"] == 96
        assert results["/api/v1/forecasts"]["body"]["total"] == 12
        plan = results[f"/api/v1/planning/production-plan?forecast_run_code={code}"]["body"]
        line = next(
            r
            for r in plan["items"]
            if r["product_code"] == "SYN-FG-002" and r["period_start"] == "2026-12-01"
        )
        for key, expected in {
            "gross_demand": "948",
            "inventory_offset": "104",
            "net_requirement": "844",
            "unmet_quantity": "844",
            "required_hours": "8.44",
            "available_hours": "6.68",
        }.items():
            assert Decimal(line[key]) == Decimal(expected), key
        capacity = results[f"/api/v1/planning/capacity?forecast_run_code={code}"]["body"]
        mixing = next(
            r
            for r in capacity["items"]
            if r["resource_code"] == "SYN-MIX" and r["period_start"] == "2026-12-01"
        )
        assert Decimal(mixing["required_hours"]) == Decimal("11.76")
        assert Decimal(mixing["available_hours"]) == 10
        assert Decimal(mixing["overload_hours"]) == Decimal("1.76")
        scenario = results[what_if]["body"]
        assert scenario["persisted"] is False and len(scenario["lines"]) == 1
        for key, expected in {
            "net_requirement": 3000,
            "allocated_quantity": 1000,
            "unmet_quantity": 2000,
            "required_hours": 30,
        }.items():
            assert Decimal(scenario["lines"][0][key]) == expected, key
        # Retain schema coverage count, not a duplicate complete OpenAPI document.
        results["/openapi.json"]["body"] = {"paths": len(results["/openapi.json"]["body"]["paths"])}
        return results
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main() -> None:
    before = database_evidence()
    with TemporaryDirectory(prefix="rivaline-phase9-") as folder:
        generated = Path(folder)
        generate(generated)
        fixture_hashes = {}
        for name, source in SOURCES.items():
            fresh = (generated / source.filename).read_bytes()
            saved = (Path("data/legacy") / source.filename).read_bytes()
            assert fresh == saved, source.filename
            fixture_hashes[name] = dict(
                rows=len(extract(generated, name)), sha256=hashlib.sha256(fresh).hexdigest()
            )
    assert sum(v["rows"] for v in fixture_hashes.values()) == 464
    responses = http_evidence()
    after = database_evidence()
    assert before == after, "Read-only validation changed the preserved dataset"
    evidence = dict(
        validated_at_utc=datetime.now(UTC).isoformat(),
        database=before,
        after_snapshot=after["snapshot"],
        fixtures=fixture_hashes,
        accepted_example=extract(Path("data/legacy"), "sales")[0],
        http=responses,
        powerbi=validate(),
        manual_desktop="User-confirmed Phase 7 evidence; not rerun by this verifier",
        safety="READ ONLY database sessions; GET and computational POST; generator only in temp",
    )
    EVIDENCE.write_text(json.dumps(evidence, default=str, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            dict(
                tables=len(before["snapshot"]["counts"]),
                rows=sum(before["snapshot"]["counts"].values()),
                sha256=before["snapshot"]["sha256"],
                http_checks=len(responses),
                fixture_rows=464,
                etl_reconciliations=len(before["etl"]),
                evidence=str(EVIDENCE),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
