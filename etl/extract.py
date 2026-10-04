"""Small, strict readers for departmental snapshots; no database writes."""

import csv
import sqlite3
from contextlib import closing
from pathlib import Path

from openpyxl import load_workbook

from etl.contracts import SOURCES


def extract(root: Path, source: str) -> list[dict[str, str]]:
    spec = SOURCES[source]
    path = root / spec.filename
    if spec.kind == "csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            rows = list(reader)
    elif spec.kind == "excel":
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            sheet = workbook["records"]
            values = iter(sheet.values)
            headers = next(values)
            rows = [dict(zip(headers, row, strict=True)) for row in values]
        finally:
            workbook.close()
    else:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute("SELECT * FROM records ORDER BY rowid")
            headers = [item[0] for item in cursor.description]
            rows = [dict(row) for row in cursor]
    if tuple(headers or ()) != spec.columns:
        raise ValueError(f"{source}: file columns do not match the source contract")
    if any(set(row) != set(spec.columns) for row in rows):
        raise ValueError(f"{source}: malformed row shape")
    return [
        {key: "" if row[key] is None else str(row[key]) for key in spec.columns} for row in rows
    ]
