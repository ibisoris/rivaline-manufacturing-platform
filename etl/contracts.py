"""Explicit legacy file contracts; only these columns are retained in quarantine."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    filename: str
    kind: str
    columns: tuple[str, ...]


COMMON = ("record_id", "business_key")
SOURCES = {
    "sales": Source(
        "legacy_sales.db",
        "sqlite",
        COMMON
        + (
            "customer",
            "product",
            "quantity",
            "unit",
            "unit_price",
            "order_date",
            "due_date",
            "status",
        ),
    ),
    "purchasing": Source(
        "purchasing_register.xlsx",
        "excel",
        COMMON
        + (
            "supplier",
            "material",
            "quantity",
            "unit",
            "unit_price",
            "order_date",
            "due_date",
            "status",
        ),
    ),
    "inventory": Source(
        "inventory_export.csv", "csv", COMMON + ("warehouse", "item", "quantity", "unit")
    ),
    "production": Source(
        "production_log.csv",
        "csv",
        COMMON
        + (
            "sales_key",
            "product",
            "bom",
            "quantity",
            "unit",
            "start_date",
            "end_date",
            "status",
            "purchase_keys",
            "consumption_kg",
            "supplier_lots",
        ),
    ),
    "quality": Source(
        "quality_inspections.xlsx",
        "excel",
        COMMON + ("batch_key", "inspection_date", "value", "unit", "status"),
    ),
    "dispatch": Source(
        "dispatch_history.csv",
        "csv",
        COMMON + ("sales_key", "batch_key", "warehouse", "quantity", "unit", "ship_date", "status"),
    ),
}
ORDER = tuple(SOURCES)
