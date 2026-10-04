"""Explicit synthetic reference policies; never change historical stock or orders."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import PlanningPolicy, RawMaterial, Warehouse
from planning.inventory import PlanningError

# Safety / reorder / target / MOQ in each synthetic material's kg unit.
POLICIES = {
    "SYN-RM-001": ("300", "500", "1000", "100"),
    "SYN-RM-002": ("500", "2500", "3000", "100"),
    "SYN-RM-003": ("2200", "2400", "3000", "1500"),
    "SYN-RM-004": ("500", "2000", "3000", "100"),
}


def seed_policies(session: Session) -> int:
    warehouse = session.scalar(select(Warehouse).where(Warehouse.code == "SYN-WH-RAW"))
    if warehouse is None:
        raise PlanningError("Synthetic master seed is required")
    count = 0
    for code, thresholds in POLICIES.items():
        material = session.scalar(select(RawMaterial).where(RawMaterial.code == code))
        if material is None or material.unit_of_measure != "kg":
            raise PlanningError("Synthetic material with kg unit is required")
        values = dict(
            zip(
                ("safety_stock", "reorder_point", "target_stock", "minimum_order_quantity"),
                map(Decimal, thresholds),
                strict=True,
            )
        )
        values.update(warehouse_id=warehouse.id, unit_of_measure="kg")
        existing = session.scalar(
            select(PlanningPolicy).where(PlanningPolicy.raw_material_id == material.id)
        )
        if existing:
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise PlanningError("Existing policy differs; refusing silent overwrite")
            continue
        session.add(
            PlanningPolicy(
                raw_material_id=material.id,
                **values,
                source_system="synthetic_planning_policy",
                source_record_id=code,
            )
        )
        count += 1
    session.flush()
    return count
