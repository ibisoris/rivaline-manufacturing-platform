"""Run-level audit, row savepoints and explicit quarantine for a bounded local ETL."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from database.models import DataQualityIssue, EtlRun
from etl.contracts import ORDER, SOURCES
from etl.extract import extract
from etl.load import load
from etl.transform import Rejected, key, validate


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def export_quarantine(session, run: EtlRun, directory: Path) -> list:
    issues = list(
        session.scalars(
            select(DataQualityIssue)
            .where(DataQualityIssue.etl_run_id == run.id)
            .order_by(DataQualityIssue.id)
        )
    )
    rows = [
        dict(
            rule=issue.rule_code,
            message=issue.message,
            severity=issue.severity,
            **(issue.details or {}),
        )
        for issue in issues
    ]
    write_json(directory / run.code / "rejected.json", rows)
    return rows


def run_pipeline(session, root: Path, quarantine: Path, sources=None) -> dict:
    selected = list(sources or ORDER)
    if (
        not selected
        or any(s not in SOURCES for s in selected)
        or len(set(selected)) != len(selected)
    ):
        raise ValueError("Select known, distinct sources")
    selected = [s for s in ORDER if s in selected]
    run = EtlRun(
        code="ETL-" + uuid4().hex,
        started_at=datetime.now(UTC),
        source_system="legacy_etl",
        source_record_id=uuid4().hex + ":" + ",".join(selected),
    )
    session.add(run)
    session.commit()  # Preserve an execution record even if extraction/load later fails.
    run_id, run_code = run.id, run.code
    report = {
        "run": run_code,
        "status": "running",
        "sources": {},
        "receipts": [],
        "extracted": 0,
        "accepted": 0,
        "rejected": 0,
        "inserted_targets": 0,
    }
    try:
        if session.get_bind().dialect.name == "sqlite":
            connection = session.connection()
            if not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql("BEGIN")
        if session.get_bind().dialect.name == "postgresql":
            # One local loader at a time; protect multi-table business-key checks.
            session.execute(text("SELECT pg_advisory_xact_lock(73120402)"))
        for source in selected:
            spec = SOURCES[source]
            path = root / spec.filename
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows = extract(root, source)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Source changed during extraction")
            stats = {
                "file": spec.filename,
                "sha256": digest,
                "extracted": len(rows),
                "accepted": 0,
                "rejected": 0,
                "inserted_targets": 0,
            }
            report["sources"][source] = stats
            report["extracted"] += len(rows)
            seen_records, seen_business = set(), set()
            for position, raw in enumerate(rows, 1):
                try:
                    record = key(raw["record_id"], "record_id")
                    business = key(raw["business_key"], "business_key")
                    if record in seen_records:
                        raise Rejected(
                            "DUPLICATE_RECORD", "Repeated source record in this snapshot"
                        )
                    if business in seen_business:
                        raise Rejected(
                            "DUPLICATE_BUSINESS_KEY", "Repeated business key in this snapshot"
                        )
                    seen_records.add(record)
                    seen_business.add(business)
                    with session.begin_nested():
                        clean = validate(session, source, raw)
                        receipts, inserted = load(session, source, clean)
                    report["receipts"].extend(receipts)
                    stats["accepted"] += 1
                    stats["inserted_targets"] += inserted
                except (Rejected, IntegrityError) as exc:
                    rule = exc.rule if isinstance(exc, Rejected) else "DATABASE_CONSTRAINT"
                    message = (
                        str(exc) if isinstance(exc, Rejected) else "Database rejected row integrity"
                    )
                    session.add(
                        DataQualityIssue(
                            etl_run_id=run_id,
                            entity_name=source,
                            rule_code=rule,
                            severity="error",
                            message=message,
                            source_system="legacy_" + source,
                            source_record_id=f"{run_code}:{position}",
                            details={
                                "source": source,
                                "file": spec.filename,
                                "position": position,
                                "record_id": raw["record_id"],
                                "business_key": raw["business_key"],
                                "detected_at": datetime.now(UTC).isoformat(),
                                "raw": raw,
                            },
                        )
                    )
                    stats["rejected"] += 1
            for field in ("accepted", "rejected", "inserted_targets"):
                report[field] += stats[field]
        run.rows_read = report["extracted"]
        run.rows_loaded = report["accepted"]  # Accepted source rows, including unchanged replay.
        run.rows_rejected = report["rejected"]
        run.finished_at = datetime.now(UTC)
        run.status = "succeeded"
        assert run.rows_read == run.rows_loaded + run.rows_rejected
        session.commit()
    except Exception as exc:
        session.rollback()  # All operational changes and row issues of this attempt roll back.
        run = session.get(EtlRun, run_id)
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.rows_read = report["extracted"]
        run.rows_loaded = 0
        run.rows_rejected = 0  # Fatal failures are not classified as row rejection.
        session.add(
            DataQualityIssue(
                etl_run_id=run_id,
                entity_name="pipeline",
                rule_code="PIPELINE_FAILURE",
                severity="error",
                message="Execution failed; operational transaction rolled back ("
                + type(exc).__name__
                + ")",
                source_system="legacy_etl",
                source_record_id=run_code,
            )
        )
        session.commit()
        raise RuntimeError(f"ETL run {run_code} failed; inspect audit records") from None
    report["status"] = "succeeded"
    try:
        export_quarantine(session, run, quarantine)
        write_json(quarantine / run_code / "summary.json", report)
    except OSError:
        # DB is committed; classify export failure separately. Rerun is safe, and row
        # quarantine can be regenerated from committed audit details.
        run.status = "failed"
        session.add(
            DataQualityIssue(
                etl_run_id=run_id,
                entity_name="quarantine",
                rule_code="EXPORT_FAILURE",
                severity="error",
                message="Business commit succeeded but local report export failed",
                source_system="legacy_etl",
                source_record_id=run_code,
            )
        )
        session.commit()
        raise RuntimeError(f"ETL run {run_code}: export failed after commit") from None
    return report
