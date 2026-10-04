"""Deterministic archived sales-demand export and strict, immutable ingestion."""

import csv
import hashlib
import json
import random
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import DemandObservation, Product
from planning.forecast_models import ForecastError, month_add, month_end

DATASET = "SYN-DEMAND-24M-V1"
SOURCE = "synthetic_demand_archive"
SEED = 20261004
START = date(2024, 10, 1)
FIELDS = (
    "record_id",
    "dataset_code",
    "product_code",
    "period_start",
    "quantity",
    "unit_of_measure",
)


def generate_history(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    seasonal = (-30, -20, 0, 15, 30, 45, 30, 20, 0, -10, -20, -35)
    rows = []
    for product, (base, trend) in enumerate(((600, 8), (850, 3), (450, 0), (700, -4)), 1):
        for step in range(24):
            period = month_add(START, step)
            spike = (
                180
                if product == 2 and step in (7, 18)
                else 120
                if product == 1 and step == 16
                else 0
            )
            total = Decimal(
                base + trend * step + seasonal[period.month - 1] + rng.randint(-40, 40) + spike
            )
            for part, share in enumerate((Decimal("0.6"), Decimal("0.4")), 1):
                rows.append(
                    dict(
                        record_id=f"{DATASET}:{product}:{period}:{part}",
                        dataset_code=DATASET,
                        product_code=f"SYN-FG-{product:03}",
                        period_start=str(period),
                        quantity=format(total * share, ".6f"),
                        unit_of_measure="kg",
                    )
                )
    path = root / "demand_history.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = dict(
        dataset_code=DATASET,
        seed=SEED,
        synthetic=True,
        rows=len(rows),
        months=24,
        period_start=str(START),
        period_end=str(month_end(month_add(START, 23))),
        products=[f"SYN-FG-{i:03}" for i in range(1, 5)],
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target=(
            "Archived booked demand; separate evaluation universe, not additional "
            "operational orders"
        ),
        formula=(
            "base + product trend * month index + fixed mild monthly effect + "
            "seeded integer noise + documented spikes"
        ),
    )
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def ingest_history(session: Session, root: Path) -> int:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    path = root / "demand_history.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if (
        manifest.get("dataset_code") != DATASET
        or manifest.get("synthetic") is not True
        or manifest.get("sha256") != digest
    ):
        raise ForecastError("History manifest identity or checksum mismatch")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ForecastError("Unexpected demand history columns")
        raw = list(reader)
    if len(raw) != 192 or manifest.get("rows") != len(raw):
        raise ForecastError("Expected 192 archived source rows")
    products = {p.code: p for p in session.scalars(select(Product))}
    expected = {(f"SYN-FG-{i:03}", month_add(START, j)) for i in range(1, 5) for j in range(24)}
    seen, months, records = set(), set(), []
    for row in raw:
        try:
            period = date.fromisoformat(row["period_start"])
            quantity = Decimal(row["quantity"])
        except (ValueError, InvalidOperation, TypeError):
            raise ForecastError("Invalid demand date or quantity") from None
        product = products.get(row["product_code"])
        key = row["record_id"]
        if (
            product is None
            or row["unit_of_measure"] != product.unit_of_measure
            or row["dataset_code"] != DATASET
            or not key.startswith(DATASET + ":")
            or key in seen
            or period.day != 1
            or period >= datetime.now(UTC).date().replace(day=1)
            or not quantity.is_finite()
            or quantity < 0
            or quantity >= Decimal("1000000000000")
            or quantity.as_tuple().exponent < -6
        ):
            raise ForecastError(
                "Invalid reference, unit, duplicate, period or quantity in demand archive"
            )
        seen.add(key)
        months.add((product.code, period))
        records.append(
            dict(
                dataset_code=DATASET,
                product_id=product.id,
                period_start=period,
                quantity=quantity,
                unit_of_measure=product.unit_of_measure,
                file_sha256=digest,
                source_system=SOURCE,
                source_record_id=key,
            )
        )
    if months != expected:
        raise ForecastError("Missing/unexpected demand periods; no zero imputation is allowed")
    existing = {
        r.source_record_id: r
        for r in session.scalars(
            select(DemandObservation).where(DemandObservation.dataset_code == DATASET)
        )
    }
    if set(existing) - seen:
        raise ForecastError("Persisted archive has unexpected source keys")
    additions = []
    for record in records:
        previous = existing.get(record["source_record_id"])
        if previous:
            if any(getattr(previous, k) != v for k, v in record.items()):
                raise ForecastError("Demand archive replay conflict; use a new dataset version")
        else:
            additions.append(DemandObservation(**record))
    session.add_all(additions)
    session.flush()
    return len(additions)
