"""Deterministic, deliberately fictional master data; no real coating recipes."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    BillOfMaterial,
    BillOfMaterialLine,
    Customer,
    Product,
    RawMaterial,
    Supplier,
    Warehouse,
)


def master_data() -> dict[str, list[dict]]:
    """Return fresh records with fixed keys; randomness is unnecessary."""
    return {
        "suppliers": [
            {"code": f"SYN-SUP-{i:03}", "name": f"Synthetic Supplier {i}"} for i in range(1, 4)
        ],
        "customers": [
            {"code": f"SYN-CUS-{i:03}", "name": f"Synthetic Customer {i}"} for i in range(1, 4)
        ],
        "warehouses": [
            {"code": "SYN-WH-RAW", "name": "Synthetic Raw Material Store"},
            {"code": "SYN-WH-FIN", "name": "Synthetic Finished Goods Store"},
        ],
        "products": [
            {"code": f"SYN-FG-{i:03}", "name": name, "unit_of_measure": "kg"}
            for i, name in enumerate(
                [
                    "Industrial Primer",
                    "Protective Topcoat",
                    "Equipment Enamel",
                    "Corrosion-Resistant Coating",
                ],
                1,
            )
        ],
        "raw_materials": [
            {
                "code": f"SYN-RM-{i:03}",
                "name": f"Synthetic {category.title()} {i}",
                "category": category,
                "unit_of_measure": "kg",
                "supplier_code": f"SYN-SUP-{(i - 1) % 3 + 1:03}",
            }
            for i, category in enumerate(["pigment", "resin", "solvent", "additive"], 1)
        ],
        "boms": [
            {
                "code": f"SYN-BOM-{i:03}",
                "product_code": f"SYN-FG-{i:03}",
                "version": 1,
                "output_quantity": Decimal("100"),
                "status": "active",
                "lines": [
                    {"material_code": f"SYN-RM-{j:03}", "quantity": Decimal("25")}
                    for j in range(1, 5)
                ],
            }
            for i in range(1, 5)
        ],
    }


def seed_master_data(session: Session) -> dict[str, int]:
    """Insert missing synthetic keys; never overwrite existing records or commit for the caller.

    Intended for single-process local setup, not concurrent imports. Existing keys are retained.
    """
    records = master_data()
    counts: dict[str, int] = {}

    def ensure(model, values, source_key):
        row = session.scalar(
            select(model).where(
                model.source_system == "synthetic_seed", model.source_record_id == source_key
            )
        )
        if row is None:
            row = model(**values, source_system="synthetic_seed", source_record_id=source_key)
            session.add(row)
            session.flush()
            counts[model.__tablename__] = counts.get(model.__tablename__, 0) + 1
        return row

    lookup = {}
    for name, model in [
        ("suppliers", Supplier),
        ("customers", Customer),
        ("warehouses", Warehouse),
        ("products", Product),
    ]:
        for values in records[name]:
            lookup[values["code"]] = ensure(model, values, values["code"]).id
    for record in records["raw_materials"]:
        values = dict(record)
        values["preferred_supplier_id"] = lookup[values.pop("supplier_code")]
        lookup[values["code"]] = ensure(RawMaterial, values, values["code"]).id
    for record in records["boms"]:
        values = dict(record)
        values["product_id"] = lookup[values.pop("product_code")]
        lines = values.pop("lines")
        bom = ensure(BillOfMaterial, values, values["code"])
        for line in lines:
            ensure(
                BillOfMaterialLine,
                {
                    "bom_id": bom.id,
                    "raw_material_id": lookup[line["material_code"]],
                    "quantity": line["quantity"],
                },
                f"{bom.code}/{line['material_code']}",
            )
    return counts
