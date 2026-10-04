"""Read-only Phase 1 PostgreSQL schema and synthetic master-data verification."""

import hashlib
import json

from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, select, text

from database.models import Base
from database.seed import master_data
from database.session import get_engine


def main() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        print("Server:", connection.scalar(text("SHOW server_version")))
        inspector = inspect(connection)
        expected = set(Base.metadata.tables)
        actual = set(inspector.get_table_names(schema="public"))
        assert expected <= actual, f"Missing tables: {sorted(expected - actual)}"
        snapshot = {}
        for name, table in Base.metadata.tables.items():
            columns = inspector.get_columns(name, schema="public")
            assert {c.name for c in table.columns} == {c["name"] for c in columns}, name
            assert inspector.get_pk_constraint(name, schema="public")["constrained_columns"] == [
                "id"
            ]
            for column in columns:
                assert column["nullable"] == table.c[column["name"]].nullable, name
            expected_fks = {
                (
                    tuple(c.name for c in fk.columns),
                    tuple(e.column.table.name for e in fk.elements),
                    tuple(e.column.name for e in fk.elements),
                )
                for fk in table.foreign_key_constraints
            }
            actual_fks = {
                (
                    tuple(fk["constrained_columns"]),
                    (fk["referred_table"],) * len(fk["referred_columns"]),
                    tuple(fk["referred_columns"]),
                )
                for fk in inspector.get_foreign_keys(name, schema="public")
            }
            assert expected_fks == actual_fks, name
            expected_unique = {
                tuple(c.name for c in constraint.columns)
                for constraint in table.constraints
                if isinstance(constraint, UniqueConstraint)
            }
            assert expected_unique == {
                tuple(c["column_names"])
                for c in inspector.get_unique_constraints(name, schema="public")
            }, name
            expected_checks = {
                engine.dialect.identifier_preparer.format_constraint(c)
                for c in table.constraints
                if isinstance(c, CheckConstraint)
            }
            assert expected_checks == {
                c["name"] for c in inspector.get_check_constraints(name, schema="public")
            }, name
            snapshot[name] = [
                dict(row)
                for row in connection.execute(select(table).order_by(table.c.id)).mappings()
            ]

        data = master_data()
        lookup = {}
        for name in ("suppliers", "customers", "warehouses", "products", "raw_materials"):
            rows = {r["code"]: r for r in snapshot[name] if r["source_system"] == "synthetic_seed"}
            assert set(rows) == {r["code"] for r in data[name]}, name
            for record in data[name]:
                row = rows[record["code"]]
                for key, value in record.items():
                    if key == "supplier_code":
                        assert row["preferred_supplier_id"] == lookup[value], name
                    else:
                        assert row[key] == value, (name, key)
                assert row["source_record_id"] == record["code"]
                lookup[row["code"]] = row["id"]
        boms = {
            r["code"]: r
            for r in snapshot["bills_of_material"]
            if r["source_system"] == "synthetic_seed"
        }
        assert set(boms) == {r["code"] for r in data["boms"]}
        for record in data["boms"]:
            bom = boms[record["code"]]
            assert bom["product_id"] == lookup[record["product_code"]]
            for key in ("version", "output_quantity", "status"):
                assert bom[key] == record[key]
            lines = [r for r in snapshot["bill_of_material_lines"] if r["bom_id"] == bom["id"]]
            assert len(lines) == len(record["lines"])
            assert {(r["raw_material_id"], r["quantity"]) for r in lines} == {
                (lookup[r["material_code"]], r["quantity"]) for r in record["lines"]
            }
        counts = {name: len(rows) for name, rows in snapshot.items()}
        print(
            f"Schema: all {len(expected)} tables, columns, nullability, "
            "primary/foreign/unique/check constraints match."
        )
        print("Master values and BOM/supplier relationships: verified.")
        print("Nonempty table counts:", {name: count for name, count in counts.items() if count})
        print("Total rows:", sum(counts.values()))
        print(
            "Data fingerprint:",
            hashlib.sha256(json.dumps(snapshot, default=str, sort_keys=True).encode()).hexdigest(),
        )
        remaining = connection.scalar(
            text("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'phase1_test_%'")
        )
        assert remaining == 0, "Temporary test schemas remain"
        print("Temporary test schemas remaining: 0")


if __name__ == "__main__":
    main()
