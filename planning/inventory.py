"""Explainable pooled-stock rules; all arithmetic is Decimal in canonical item units."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import models as m
from planning.contracts import (
    Position,
    Recommendation,
    Requirement,
    ScenarioMaterial,
    ScenarioQuery,
    ScenarioResult,
)

ALGORITHM = "pooled-conservative-v1"
SOURCE = "phase4_reorder_v1"
ZERO = Decimal(0)
PRECISION = Decimal("0.000001")


class PlanningError(Exception):
    """Actionable planning input conflict; safe for API clients."""


def reorder_quantity(
    projected: Decimal, reorder: Decimal, target: Decimal, minimum: Decimal
) -> Decimal:
    return max(target - projected, minimum) if projected < reorder else ZERO


def explode(quantity: Decimal, output: Decimal, component: Decimal) -> Decimal:
    if quantity <= 0 or output <= 0 or component <= 0:
        raise PlanningError("BOM and requested quantities must be positive")
    return (quantity * component / output).quantize(PRECISION, rounding=ROUND_HALF_UP)


def explain(position: Position) -> str:
    p = position
    basis = (
        f"{p.item_code}: projected stock {p.projected_quantity} {p.unit_of_measure} = "
        f"on hand {p.on_hand_quantity} - reserved {p.reserved_quantity} "
        f"+ assumed confirmed incoming {p.incoming_quantity} - requirements {p.required_quantity}. "
    )
    if p.risk_status == "invalid_policy":
        return basis + "Policy unit differs from the item unit; correct policy before ordering."
    if p.recommended_quantity is None:
        return basis + "No material reorder policy; no purchasing recommendation calculated."
    if p.recommended_quantity > 0:
        return basis + (
            f"Below reorder point {p.reorder_point} (safety {p.safety_stock}); propose "
            f"{p.recommended_quantity} to restore target {p.target_stock}, "
            f"respecting minimum order {p.minimum_order_quantity}."
        )
    return basis + f"At or above reorder point {p.reorder_point}; no order proposed."


def validate_boms(session: Session) -> None:
    missing = session.scalar(
        select(m.ProductionOrder.id)
        .where(
            m.ProductionOrder.status.in_(("planned", "released")),
            ~select(m.BillOfMaterialLine.id)
            .where(m.BillOfMaterialLine.bom_id == m.ProductionOrder.bom_id)
            .exists(),
        )
        .limit(1)
    )
    if missing is not None:
        raise PlanningError(
            "An open production order has an empty BOM; requirements are incomplete"
        )


def positions(session: Session) -> list[Position]:
    validate_boms(session)
    rows = session.execute(text("SELECT * FROM vw_inventory_risk ORDER BY item_type, item_id"))
    result = [Position.model_validate(row) for row in rows.mappings()]
    for row in result:
        row.explanation = explain(row)
    return result


def requirements(session: Session) -> list[Requirement]:
    validate_boms(session)
    return [
        Requirement.model_validate(row)
        for row in session.execute(
            text(
                "SELECT * FROM vw_material_requirements "
                "ORDER BY production_order_id, raw_material_id"
            )
        ).mappings()
    ]


def scenario(session: Session, query: ScenarioQuery) -> ScenarioResult:
    product = session.get(m.Product, query.product_id)
    if product is None:
        raise LookupError("Product not found")
    if query.unit_of_measure != product.unit_of_measure:
        raise PlanningError(
            "Requested unit must match the product canonical unit; no conversion exists"
        )
    statement = select(m.BillOfMaterial).where(
        m.BillOfMaterial.product_id == product.id, m.BillOfMaterial.status == "active"
    )
    if query.bom_id is not None:
        statement = statement.where(m.BillOfMaterial.id == query.bom_id)
    boms = list(session.scalars(statement))
    if len(boms) != 1:
        raise PlanningError(
            "Select exactly one active BOM for this product; use bom_id if ambiguous"
        )
    bom = boms[0]
    lines = list(
        session.scalars(
            select(m.BillOfMaterialLine)
            .where(m.BillOfMaterialLine.bom_id == bom.id)
            .order_by(m.BillOfMaterialLine.raw_material_id)
        )
    )
    if not lines:
        raise PlanningError("Selected BOM has no material lines")
    stock = {p.item_id: p for p in positions(session) if p.item_type == "raw_material"}
    existing = requirements(session)
    materials = []
    for line in lines:
        p = stock[line.raw_material_id]
        incremental = explode(query.quantity, bom.output_quantity, line.quantity)
        projected = p.projected_quantity - incremental
        quantity = (
            None
            if p.recommended_quantity is None
            else reorder_quantity(
                projected, p.reorder_point, p.target_stock, p.minimum_order_quantity
            )
        )
        materials.append(
            ScenarioMaterial(
                raw_material_id=p.item_id,
                material_code=p.item_code,
                unit_of_measure=p.unit_of_measure,
                incremental_requirement=incremental,
                current_available=p.available_quantity,
                baseline_projected=p.projected_quantity,
                scenario_projected=projected,
                shortage_quantity=max(-projected, ZERO),
                additional_shortage=max(-projected, ZERO) - p.shortage_quantity,
                recommended_quantity=quantity,
                affected_production_order_ids=sorted(
                    {
                        r.production_order_id
                        for r in existing
                        if r.raw_material_id == p.item_id and r.required_quantity > 0
                    }
                ),
                explanation=(
                    f"Additional {query.quantity} {product.unit_of_measure} requires "
                    f"{incremental} {p.unit_of_measure} = quantity * {line.quantity} / "
                    f"BOM output {bom.output_quantity}. "
                    f"Pooled projected stock becomes {projected}; "
                    "existing requirements remain included; no orders or stock are changed."
                ),
            )
        )
    return ScenarioResult(
        product_id=product.id,
        bom_id=bom.id,
        quantity=query.quantity,
        unit_of_measure=product.unit_of_measure,
        materials=materials,
    )


def generate(session: Session) -> tuple[m.PlanningRun, bool]:
    """Caller owns transaction. Exact-input replay returns the original immutable run."""
    stock = positions(session)
    if any(p.risk_status == "invalid_policy" for p in stock):
        raise PlanningError("Policy unit mismatch; no recommendations persisted")
    needs = requirements(session)
    payload = {
        "algorithm_version": ALGORITHM,
        "positions": [p.model_dump(mode="json") for p in stock],
        "requirements": [r.model_dump(mode="json") for r in needs],
    }
    code = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = session.scalar(select(m.PlanningRun).where(m.PlanningRun.code == code))
    if previous is not None:
        return previous, False
    run = m.PlanningRun(
        code=code,
        generated_at=datetime.now(UTC),
        algorithm_version=ALGORITHM,
        inputs=payload,
        source_system=SOURCE,
        source_record_id=code,
    )
    session.add(run)
    session.flush()
    for p in stock:
        if p.recommended_quantity is not None and p.recommended_quantity > 0:
            session.add(
                m.ReorderRecommendation(
                    raw_material_id=p.item_id,
                    warehouse_id=p.destination_warehouse_id,
                    quantity=p.recommended_quantity,
                    reason=p.explanation,
                    generated_at=run.generated_at,
                    status="proposed",
                    source_system=SOURCE,
                    source_record_id=f"{code}:{p.item_id}",
                )
            )
    session.flush()
    return run, True


def recommendations(session: Session) -> list[Recommendation]:
    runs = {r.code: r for r in session.scalars(select(m.PlanningRun))}
    result = []
    for row in session.scalars(
        select(m.ReorderRecommendation).order_by(m.ReorderRecommendation.id)
    ):
        value = Recommendation.model_validate(row)
        run = (
            runs.get((row.source_record_id or "").split(":")[0])
            if row.source_system == SOURCE
            else None
        )
        if run:
            value.run_code, value.algorithm_version = run.code, run.algorithm_version
            value.input_position = next(
                Position.model_validate(p)
                for p in run.inputs["positions"]
                if p["item_type"] == "raw_material" and p["item_id"] == row.raw_material_id
            )
            value.affected_requirements = [
                Requirement.model_validate(r)
                for r in run.inputs["requirements"]
                if r["raw_material_id"] == row.raw_material_id
            ]
        result.append(value)
    return result
