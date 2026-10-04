"""Reconcile committed target values with accepted-row receipts; demonstrate lineage."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from database import models as m
from etl.contracts import SOURCES
from etl.extract import extract
from etl.load import scalar


def reconcile(session, summary: Path, root: Path | None = None) -> dict:
    report = json.loads(summary.read_text(encoding="utf-8"))
    run = session.scalar(select(m.EtlRun).where(m.EtlRun.code == report["run"]))
    failures = []
    if run is None:
        return {"ok": False, "failures": ["Missing ETL run"]}
    if run.status != "succeeded" or report["status"] != "succeeded":
        return {"ok": False, "run": run.code, "failures": ["Run is not successful"]}
    if (run.rows_read, run.rows_loaded, run.rows_rejected) != (
        report["extracted"],
        report["accepted"],
        report["rejected"],
    ):
        failures.append("Audit counters differ from summary")
    if report["extracted"] != report["accepted"] + report["rejected"]:
        failures.append("Extracted != accepted + rejected")
    for source, stats in report["sources"].items():
        if stats["extracted"] != stats["accepted"] + stats["rejected"]:
            failures.append(f"Source counts differ: {source}")
    issues = list(
        session.scalars(select(m.DataQualityIssue).where(m.DataQualityIssue.etl_run_id == run.id))
    )
    quarantine = json.loads(summary.with_name("rejected.json").read_text(encoding="utf-8"))
    if len(issues) != report["rejected"] or len(quarantine) != len(issues):
        failures.append("Quarantine/issue counts differ")
    expected_rejections = {
        (i.details["source"], i.details["position"], i.rule_code) for i in issues
    }
    if expected_rejections != {(r["source"], r["position"], r["rule"]) for r in quarantine}:
        failures.append("Quarantine identities differ")
    expected_totals, actual_totals = {}, {}
    identities = set()
    for receipt in report["receipts"]:
        table = m.Base.metadata.tables[receipt["table"]]
        identity = (table.name, receipt["source_system"], receipt["source_record_id"])
        if identity in identities:
            failures.append("Duplicate target receipt")
        identities.add(identity)
        row = (
            session.execute(
                select(table).where(
                    table.c.source_system == receipt["source_system"],
                    table.c.source_record_id == receipt["source_record_id"],
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            failures.append(f"Missing target {table.name}")
            continue
        for field, expected in receipt["values"].items():
            if scalar(row[field]) != expected:
                failures.append(f"Changed target {table.name}.{field}")
            if field in {"quantity", "planned_quantity", "actual_quantity"}:
                key = table.name + "." + field
                expected_totals[key] = expected_totals.get(key, Decimal(0)) + Decimal(expected)
                actual_totals[key] = actual_totals.get(key, Decimal(0)) + row[field]
    if actual_totals != expected_totals:
        failures.append("Quantity totals differ")
    source_totals = {}
    if root is not None:
        mapping = {
            "sales": ["sales_order_lines.quantity"],
            "purchasing": ["purchase_order_lines.quantity"],
            "inventory": ["inventory.quantity"],
            "production": [
                "production_orders.planned_quantity",
                "production_batches.actual_quantity",
            ],
            "dispatch": ["shipment_lines.quantity"],
        }
        for source, stats in report["sources"].items():
            path = root / SOURCES[source].filename
            if hashlib.sha256(path.read_bytes()).hexdigest() != stats["sha256"]:
                failures.append(f"Source changed since execution: {source}")
                continue
            rows = extract(root, source)
            rejected_positions = {r["position"] for r in quarantine if r["source"] == source}
            accepted = [
                row for position, row in enumerate(rows, 1) if position not in rejected_positions
            ]
            if len(rows) != stats["extracted"] or len(accepted) != stats["accepted"]:
                failures.append(f"Source row counts differ: {source}")
            if source == "quality":
                continue
            # Independently total original accepted source values, not loader receipts.
            total = sum(
                (
                    Decimal(row["quantity"].strip())
                    * (
                        Decimal("0.001")
                        if row["unit"].strip().lower() in {"g", "grams"}
                        else Decimal(1)
                    )
                    for row in accepted
                ),
                Decimal(0),
            )
            for target in mapping[source]:
                source_totals[target] = total
            if source == "production":
                source_totals["batch_material_consumption.quantity"] = sum(
                    (
                        Decimal(value)
                        for row in accepted
                        for value in row["consumption_kg"].split("|")
                    ),
                    Decimal(0),
                )
        if source_totals != actual_totals:
            failures.append("Independent source-to-target quantity totals differ")
    return {
        "source_totals_kg": {k: scalar(v) for k, v in source_totals.items()},
        "source_files_verified": root is not None,
        "ok": not failures,
        "run": run.code,
        "extracted": run.rows_read,
        "accepted": run.rows_loaded,
        "rejected": run.rows_rejected,
        "target_receipts": len(identities),
        "failures": failures,
        "expected_totals_kg": {k: scalar(v) for k, v in expected_totals.items()},
        "actual_totals_kg": {k: scalar(v) for k, v in actual_totals.items()},
    }


def business_snapshot(session) -> dict:
    snapshot = {}
    for name, table in m.Base.metadata.tables.items():
        if name not in m.PHASE1_TABLES or name in {"etl_runs", "data_quality_issues"}:
            continue
        snapshot[name] = [
            {k: scalar(v) for k, v in row.items()}
            for row in session.execute(select(table).order_by(table.c.id)).mappings()
        ]
    return {
        "counts": {k: len(v) for k, v in snapshot.items()},
        "sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
    }


def trace(session, order_code: str = "SO-0001") -> dict:
    order = session.scalar(select(m.SalesOrder).where(m.SalesOrder.code == order_code))
    if order is None:
        raise ValueError("Order not found")
    customer = session.get(m.Customer, order.customer_id)
    result = {"order": order.code, "customer": customer.code, "batches": []}
    lines = list(
        session.scalars(select(m.SalesOrderLine).where(m.SalesOrderLine.sales_order_id == order.id))
    )
    for line in lines:
        product = session.get(m.Product, line.product_id)
        orders = list(
            session.scalars(
                select(m.ProductionOrder).where(m.ProductionOrder.sales_order_line_id == line.id)
            )
        )
        for production in orders:
            for batch in session.scalars(
                select(m.ProductionBatch).where(
                    m.ProductionBatch.production_order_id == production.id
                )
            ):
                quality = list(
                    session.scalars(
                        select(m.QualityInspection).where(
                            m.QualityInspection.production_batch_id == batch.id
                        )
                    )
                )
                materials = []
                for consumption in session.scalars(
                    select(m.BatchMaterialConsumption).where(
                        m.BatchMaterialConsumption.production_batch_id == batch.id
                    )
                ):
                    material = session.get(m.RawMaterial, consumption.raw_material_id)
                    purchase_line = session.get(
                        m.PurchaseOrderLine, consumption.purchase_order_line_id
                    )
                    purchase = session.get(m.PurchaseOrder, purchase_line.purchase_order_id)
                    supplier = session.get(m.Supplier, purchase.supplier_id)
                    materials.append(
                        {
                            "material": material.code,
                            "supplier": supplier.code,
                            "purchase_order": purchase.code,
                            "supplier_lot": consumption.supplier_lot_code,
                            "quantity_kg": scalar(consumption.quantity),
                        }
                    )
                result["batches"].append(
                    {
                        "product": product.code,
                        "production_order": production.code,
                        "batch": batch.code,
                        "quality": [q.result for q in quality],
                        "materials": materials,
                    }
                )
    return result
