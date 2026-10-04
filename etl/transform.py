"""Normalisation and explainable validation against the existing operational contracts."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from database import models as m


class Rejected(ValueError):
    def __init__(self, rule: str, message: str):
        self.rule = rule
        super().__init__(message)


def required(value: str, field: str) -> str:
    value = value.strip()
    if not value:
        raise Rejected("MISSING_FIELD", f"{field} is required")
    return value


def identifier(value: str) -> str:
    text = required(value, "identifier").upper()
    compact = re.sub(r"[-_ ]", "", text)
    match = re.fullmatch(r"(?:SYN)?(RM|FG|SUP|CUS|BOM)([0-9]{3})", compact)
    if match:
        return f"SYN-{match[1]}-{match[2]}"
    return text


def key(value: str, field: str) -> str:
    value = required(value, field).upper()
    if len(value) > 40 or not re.fullmatch(r"[A-Z0-9_-]+", value):
        raise Rejected("INVALID_IDENTIFIER", f"{field} must be a short alphanumeric business key")
    return value


def number(value: str, field: str, positive: bool = True) -> Decimal:
    value = required(value, field)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise Rejected("INVALID_QUANTITY", f"{field} must be a decimal") from None
    if (
        not result.is_finite()
        or result < 0
        or (positive and result == 0)
        or result >= Decimal("1000000000000")
        or result.as_tuple().exponent < -6
    ):
        raise Rejected("INVALID_QUANTITY", f"{field} must fit a nonnegative six-decimal quantity")
    return result


def day(value: str, field: str) -> date:
    value = required(value, field)
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError:
        raise Rejected("INVALID_DATE", f"{field} must be a valid ISO date") from None


def timestamp(value: date) -> datetime:
    return datetime.combine(value, datetime.min.time(), tzinfo=UTC)


def ref(session, model, code: str):
    found = session.scalar(select(model).where(model.code == identifier(code)))
    if found is None:
        raise Rejected("INVALID_REFERENCE", f"Unknown {model.__tablename__} reference")
    return found


def sales_line(session, code: str):
    order = ref(session, m.SalesOrder, code)
    line = session.scalar(
        select(m.SalesOrderLine).where(
            m.SalesOrderLine.sales_order_id == order.id, m.SalesOrderLine.line_number == 1
        )
    )
    if line is None:
        raise Rejected("INVALID_REFERENCE", "Sales order line is missing")
    return order, line


def validate(session, source: str, row: dict) -> dict:
    result = {k: v.strip() for k, v in row.items()}
    result["record_id"] = key(row["record_id"], "record_id")
    result["business_key"] = key(row["business_key"], "business_key")
    if source != "quality":
        unit = required(row["unit"], "unit").lower()
        factors = {
            "kg": Decimal(1),
            "kilograms": Decimal(1),
            "g": Decimal("0.001"),
            "grams": Decimal("0.001"),
        }
        if unit not in factors:
            raise Rejected("INVALID_UNIT", "Only explicit mass units kg/g are convertible")
        result["quantity"] = (
            number(row["quantity"], "quantity", source != "inventory") * factors[unit]
        )
        if result["quantity"].as_tuple().exponent < -6:
            raise Rejected("INVALID_QUANTITY", "Converted quantity exceeds six-decimal precision")
    if source in ("sales", "purchasing"):
        result["order_date"] = day(row["order_date"], "order_date")
        result["due_date"] = day(row["due_date"], "due_date")
        if result["due_date"] < result["order_date"]:
            raise Rejected("DATE_ORDER", "Due date precedes order date")
        price = number(row["unit_price"], "unit_price", False)
        if price != price.quantize(Decimal("0.01")):
            raise Rejected("INVALID_QUANTITY", "Price must have at most two decimal places")
        result["unit_price"] = price
        if source == "sales":
            result["party"] = ref(session, m.Customer, row["customer"])
            result["item"] = ref(session, m.Product, row["product"])
            allowed = {"open", "confirmed", "fulfilled", "cancelled"}
        else:
            result["party"] = ref(session, m.Supplier, row["supplier"])
            result["item"] = ref(session, m.RawMaterial, row["material"])
            allowed = {"open", "confirmed", "received", "cancelled"}
    elif source == "inventory":
        result["warehouse_ref"] = ref(session, m.Warehouse, row["warehouse"])
        item = identifier(row["item"])
        model = m.RawMaterial if item.startswith("SYN-RM-") else m.Product
        result["item"] = ref(session, model, item)
        allowed = set()
    elif source == "production":
        result["order"], result["line"] = sales_line(session, row["sales_key"])
        result["item"] = ref(session, m.Product, row["product"])
        result["bom_ref"] = ref(session, m.BillOfMaterial, row["bom"])
        if (
            result["line"].product_id != result["item"].id
            or result["bom_ref"].product_id != result["item"].id
        ):
            raise Rejected("ITEM_MISMATCH", "Sales product, production product and BOM must agree")
        if result["quantity"] > result["line"].quantity:
            raise Rejected("QUANTITY_LIMIT", "Batch quantity exceeds sales demand")
        result["start_date"] = day(row["start_date"], "start_date")
        result["end_date"] = day(row["end_date"], "end_date")
        if (
            result["end_date"] < result["start_date"]
            or result["start_date"] < result["order"].order_date
        ):
            raise Rejected("DATE_ORDER", "Production dates precede order/start")
        purchases = []
        for code in required(row["purchase_keys"], "purchase_keys").split("|"):
            order = ref(session, m.PurchaseOrder, code)
            line = session.scalar(
                select(m.PurchaseOrderLine).where(
                    m.PurchaseOrderLine.purchase_order_id == order.id,
                    m.PurchaseOrderLine.line_number == 1,
                )
            )
            if line is None:
                raise Rejected("INVALID_REFERENCE", "Purchase line is missing")
            if order.status != "received" or order.expected_date > result["start_date"]:
                raise Rejected("DATE_ORDER", "Material must be received before production")
            purchases.append(line)
        bom_lines = list(
            session.scalars(
                select(m.BillOfMaterialLine).where(
                    m.BillOfMaterialLine.bom_id == result["bom_ref"].id
                )
            )
        )
        if len(purchases) != len(bom_lines) or {p.raw_material_id for p in purchases} != {
            b.raw_material_id for b in bom_lines
        }:
            raise Rejected(
                "ITEM_MISMATCH", "Purchase lines must cover each BOM material exactly once"
            )
        quantities = [
            number(v, "consumption_kg")
            for v in required(row["consumption_kg"], "consumption_kg").split("|")
        ]
        lots = [
            key(v, "supplier_lot")
            for v in required(row["supplier_lots"], "supplier_lots").split("|")
        ]
        if len(quantities) != len(purchases) or len(lots) != len(purchases):
            raise Rejected(
                "ITEM_MISMATCH", "Consumption and lot lists must align with purchase lines"
            )
        result["consumption"] = []
        for purchase, quantity, lot in zip(purchases, quantities, lots, strict=True):
            if quantity > purchase.quantity:
                raise Rejected("QUANTITY_LIMIT", "Material consumption exceeds purchase quantity")
            result["consumption"].append((purchase, quantity, lot))
        if sum(quantities) != result["quantity"]:
            raise Rejected("MASS_BALANCE", "Synthetic zero-loss batch inputs must equal output")
        allowed = {"quarantined", "released", "rejected"}
    elif source == "quality":
        result["batch"] = ref(session, m.ProductionBatch, row["batch_key"])
        result["inspection_date"] = day(row["inspection_date"], "inspection_date")
        order = session.get(m.ProductionOrder, result["batch"].production_order_id)
        if result["inspection_date"] < order.planned_end:
            raise Rejected("DATE_ORDER", "Inspection precedes batch completion")
        result["value"] = number(row["value"], "value", False)
        if row["unit"].strip().lower() != "score":
            raise Rejected("INVALID_UNIT", "Synthetic QC measurements use score")
        allowed = {"pass", "fail", "pending"}
    else:
        result["order"], result["line"] = sales_line(session, row["sales_key"])
        result["batch"] = ref(session, m.ProductionBatch, row["batch_key"])
        result["warehouse_ref"] = ref(session, m.Warehouse, row["warehouse"])
        result["ship_date"] = day(row["ship_date"], "ship_date")
        production = session.get(m.ProductionOrder, result["batch"].production_order_id)
        if result["ship_date"] < max(result["order"].order_date, production.planned_end):
            raise Rejected("DATE_ORDER", "Shipment precedes customer order or batch completion")
        if result["line"].product_id != result["batch"].product_id:
            raise Rejected("ITEM_MISMATCH", "Shipment batch and sales product differ")
        if result["quantity"] > min(result["line"].quantity, result["batch"].actual_quantity):
            raise Rejected("QUANTITY_LIMIT", "Shipment exceeds order or batch quantity")
        inspections = list(
            session.scalars(
                select(m.QualityInspection).where(
                    m.QualityInspection.production_batch_id == result["batch"].id
                )
            )
        )
        if (
            result["batch"].status != "released"
            or not inspections
            or any(
                q.result != "pass" or q.inspected_at.date() > result["ship_date"]
                for q in inspections
            )
        ):
            raise Rejected(
                "QUALITY_HOLD", "Dispatch requires released batch and prior passed inspections"
            )
        allowed = {"pending", "dispatched", "delivered", "cancelled"}
    if "item" in result and result["item"].unit_of_measure != "kg":
        raise Rejected(
            "INVALID_UNIT", "Item canonical unit is not supported by this mass-only source"
        )
    if allowed:
        result["status"] = required(row["status"], "status").lower()
        if result["status"] not in allowed:
            raise Rejected("INVALID_STATUS", "Status is not recognised for this source")
    return result
