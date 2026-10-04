"""Fixed-seed fictional exports. Reset overwrites only the six owned fixture files."""

import csv
import hashlib
import json
import random
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook

from etl.contracts import SOURCES


def records() -> tuple[dict, list]:
    rng = random.Random(20261003)
    data = {name: [] for name in SOURCES}
    for i in range(1, 49):
        day = date(2026, 1, 1) + timedelta(days=i)
        product = f"SYN-FG-{(i - 1) % 4 + 1:03}"
        qty = rng.choice([100, 200, 300])
        sale = f"SO-{i:04}"
        batch = f"BATCH-{i:04}"
        common = {"quantity": str(qty), "unit": " KG " if i % 2 else "kg"}
        data["sales"].append(
            dict(
                record_id=f"SALE-{i:04}",
                business_key=sale,
                customer=f"SYN-CUS-{(i - 1) % 3 + 1:03}",
                product=product,
                **common,
                unit_price="12.50",
                order_date=str(day),
                due_date=str(day + timedelta(days=7)),
                status=" Confirmed ",
            )
        )
        purchase_keys = []
        for j in range(1, 5):
            key = f"PO-{i:04}-{j}"
            purchase_keys.append(key)
            material = [f"RM-{j:03}", f"rm{j:03}", f"RM_{j:03}"][i % 3]
            data["purchasing"].append(
                dict(
                    record_id=key,
                    business_key=key,
                    supplier=f"SYN-SUP-{(j - 1) % 3 + 1:03}",
                    material=material,
                    quantity=str(qty // 4),
                    unit="kg",
                    unit_price="2.00",
                    order_date=str(day - timedelta(days=3)),
                    due_date=str(day),
                    status="received",
                )
            )
        data["production"].append(
            dict(
                record_id=f"PROD-{i:04}",
                business_key=batch,
                sales_key=sale,
                product=product,
                bom=f"SYN-BOM-{(i - 1) % 4 + 1:03}",
                **common,
                start_date=str(day + timedelta(days=1)),
                end_date=str(day + timedelta(days=2)),
                status="released",
                purchase_keys="|".join(purchase_keys),
                consumption_kg="|".join([str(qty // 4)] * 4),
                supplier_lots="|".join(f"SYN-LOT-{i:04}-{j}" for j in range(1, 5)),
            )
        )
        data["quality"].append(
            dict(
                record_id=f"QC-{i:04}",
                business_key=f"QC-{i:04}",
                batch_key=batch,
                inspection_date=str(day + timedelta(days=3)),
                value=str(rng.randint(50, 80)),
                unit="score",
                status=" PASS ",
            )
        )
        data["dispatch"].append(
            dict(
                record_id=f"SHIP-{i:04}",
                business_key=f"SHIP-{i:04}",
                sales_key=sale,
                batch_key=batch,
                warehouse="SYN-WH-FIN",
                **common,
                ship_date=str(day + timedelta(days=4)),
                status="delivered",
            )
        )
    for i in range(1, 33):
        raw = i <= 16
        data["inventory"].append(
            dict(
                record_id=f"STOCK-{i:04}",
                business_key=f"LOT-{i:04}",
                warehouse="SYN-WH-RAW" if raw else "SYN-WH-FIN",
                item=f"{'rm' if raw else 'fg'}{(i - 1) % 4 + 1:03}",
                quantity="500000",
                unit="grams",
            )
        )
    cases = {
        "sales": [
            ("customer", "", "MISSING_FIELD"),
            ("product", "FG-999", "INVALID_REFERENCE"),
            ("order_date", "2026-02-30", "INVALID_DATE"),
            ("quantity", "0", "INVALID_QUANTITY"),
            ("status", "lost", "INVALID_STATUS"),
        ],
        "purchasing": [
            ("supplier", "", "MISSING_FIELD"),
            ("material", "RM-999", "INVALID_REFERENCE"),
            ("quantity", "-1", "INVALID_QUANTITY"),
            ("due_date", "2025-01-01", "DATE_ORDER"),
            ("unit", "litres", "INVALID_UNIT"),
        ],
        "inventory": [
            ("warehouse", "", "MISSING_FIELD"),
            ("item", "RM-999", "INVALID_REFERENCE"),
            ("quantity", "-1", "INVALID_QUANTITY"),
            ("unit", "litres", "INVALID_UNIT"),
            ("quantity", "NaN", "INVALID_QUANTITY"),
        ],
        "production": [
            ("sales_key", "SO-9999", "INVALID_REFERENCE"),
            ("bom", "BOM-999", "INVALID_REFERENCE"),
            ("quantity", "0", "INVALID_QUANTITY"),
            ("end_date", "2025-01-01", "DATE_ORDER"),
            ("status", "lost", "INVALID_STATUS"),
        ],
        "quality": [
            ("batch_key", "BATCH-9999", "INVALID_REFERENCE"),
            ("inspection_date", "yesterday", "INVALID_DATE"),
            ("unit", "litres", "INVALID_UNIT"),
            ("status", "maybe", "INVALID_STATUS"),
            ("value", "", "MISSING_FIELD"),
        ],
        "dispatch": [
            ("sales_key", "SO-9999", "INVALID_REFERENCE"),
            ("batch_key", "BATCH-9999", "INVALID_REFERENCE"),
            ("ship_date", "2025-01-01", "DATE_ORDER"),
            ("quantity", "0", "INVALID_QUANTITY"),
            ("status", "lost", "INVALID_STATUS"),
        ],
    }
    manifest = []
    for source, rows in data.items():
        original = dict(rows[0])
        mutations = [
            (None, None, "DUPLICATE_RECORD"),
            ("business_key", original["business_key"], "DUPLICATE_BUSINESS_KEY"),
            ("record_id", "", "MISSING_FIELD"),
        ] + cases[source]
        for number, (field, value, rule) in enumerate(mutations, 1):
            row = dict(original)
            if number != 1:
                row.update(
                    record_id=f"BAD-{source.upper()}-{number}",
                    business_key=f"BAD-{source.upper()}-{number}",
                )
            if field:
                row[field] = value
            rows.append(row)
            manifest.append(
                dict(
                    source=source,
                    position=len(rows),
                    record_id=row["record_id"],
                    business_key=row["business_key"],
                    rule=rule,
                    field=field,
                    value=value,
                )
            )
    return data, manifest


def generate(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    data, defects = records()
    for name, spec in SOURCES.items():
        target = root / spec.filename
        # Build beside the destination then replace only known owned fixture files.
        with TemporaryDirectory(dir=root) as staging:
            temporary = Path(staging) / spec.filename
            rows = data[name]
            if spec.kind == "csv":
                with temporary.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=spec.columns)
                    writer.writeheader()
                    writer.writerows(rows)
            elif spec.kind == "sqlite":
                with closing(sqlite3.connect(temporary)) as connection:
                    columns = ", ".join(f'"{column}" TEXT' for column in spec.columns)
                    connection.execute(f"CREATE TABLE records ({columns})")
                    marks = ",".join("?" for _ in spec.columns)
                    connection.executemany(
                        f"INSERT INTO records VALUES ({marks})",
                        [tuple(row[c] for c in spec.columns) for row in rows],
                    )
                    connection.commit()
            else:
                workbook = Workbook()
                workbook.properties.created = datetime(2026, 1, 1)
                workbook.properties.modified = datetime(2026, 1, 1)
                sheet = workbook.active
                sheet.title = "records"
                sheet.append(spec.columns)
                for row in rows:
                    sheet.append([row[c] for c in spec.columns])
                workbook.save(temporary)
                # XLSX is a zip: freeze member timestamps and core modified metadata too.
                normalized = Path(staging) / "normalized.xlsx"
                with ZipFile(temporary) as src, ZipFile(normalized, "w", ZIP_DEFLATED) as dst:
                    for member in sorted(src.namelist()):
                        payload = src.read(member)
                        if member == "docProps/core.xml":
                            import re

                            payload = re.sub(
                                rb"(<dcterms:modified[^>]*>).*?(</dcterms:modified>)",
                                rb"\g<1>2026-01-01T00:00:00Z\g<2>",
                                payload,
                            )
                        info = ZipInfo(member, date_time=(2026, 1, 1, 0, 0, 0))
                        info.compress_type = ZIP_DEFLATED
                        dst.writestr(info, payload)
                normalized.replace(temporary)
            temporary.replace(target)
    manifest = {
        "synthetic": True,
        "seed": 20261003,
        "valid_rows": 416,
        "rejected_rows": len(defects),
        "defects": defects,
        "sources": {
            name: {
                "file": spec.filename,
                "rows": len(data[name]),
                "valid": len(data[name]) - 8,
                "sha256": hashlib.sha256((root / spec.filename).read_bytes()).hexdigest(),
            }
            for name, spec in SOURCES.items()
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
