"""Shared KPI contracts backed by the same views consumed by reporting tools."""

from sqlalchemy import text
from sqlalchemy.orm import Session

VIEW_NAMES = (
    "vw_inventory_position",
    "vw_order_fulfilment",
    "vw_production_performance",
    "vw_quality_performance",
    "vw_supplier_material_flow",
    "vw_data_quality_summary",
    "vw_operations_kpis",
    "vw_operations_quantities",
)


def operations_kpis(session: Session) -> dict:
    counters = dict(session.execute(text("SELECT * FROM vw_operations_kpis")).mappings().one())
    counters["quantities"] = list(
        session.execute(
            text(
                "SELECT metric, item_type, unit_of_measure, quantity FROM vw_operations_quantities "
                "ORDER BY metric, item_type, unit_of_measure"
            )
        ).mappings()
    )
    return counters
