"""Deterministic monthly plans. Only save_forecast_plan writes decision-support evidence."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models as m
from planning.contracts import ScenarioQuery
from planning.forecasting import verify_saved
from planning.inventory import PlanningError, explode, positions, scenario
from planning.production_contracts import (
    CapacityResult,
    Demand,
    MaterialNeed,
    PlanLine,
    PlanResult,
    ProposedBatch,
    WhatIf,
)

VERSION = "production-plan-v1"
SOURCE = "phase6_production_v1"
ZERO = Decimal(0)
SIX = Decimal("0.000001")
EXPLANATIONS = [
    "Synthetic proposed plan, not an approved production schedule. No execution records changed.",
    "Forecast and manual demand are separate alternative scenarios, never added together. "
    "Historical orders are not forecast demand. Unfulfilled confirmed sales are protected in "
    "the Phase 4 stock baseline; this model does not generate another plan for those orders.",
    "Finished stock is pooled available less existing confirmed requirements, floored at zero. "
    "Reservations and requirements remain conservatively additive. No unposted production supply.",
    "Materials reuse Phase 4 projected stock, including assumed wholly outstanding confirmed "
    "purchases and existing production requirements. All assumed incoming is available at start; "
    "receipt dates, expiry and QC release are not guaranteed.",
    "Earlier month, then ascending product priority, then product code. Whole batches allocate "
    "only when both materials and residual monthly capacity suffice. Unmet demand is explicit, "
    "not silently rolled into another month. Allocated minimum-batch surplus carries forward.",
    "Monthly resource hours are residual capacity after external commitments, repeated each month. "
    "One compatible resource per product; no routing, setup, downtime or shop-floor scheduling.",
]


def rounded(value: Decimal) -> Decimal:
    return value.quantize(SIX, rounding=ROUND_HALF_UP)


def hours(quantity: Decimal, rate: Decimal) -> Decimal:
    # Round up to one microhour so allocation never exceeds exact processing capacity.
    return (quantity / rate).quantize(SIX, rounding=ROUND_CEILING)


def utilisation(required: Decimal, available: Decimal) -> Decimal | None:
    return (required * 100 / available).quantize(Decimal("0.01")) if available else None


def batch_sizes(
    net: Decimal, minimum: Decimal, preferred: Decimal, maximum: Decimal
) -> list[Decimal]:
    if net < 0 or not (ZERO < minimum <= preferred <= maximum):
        raise PlanningError("Invalid net demand or batch bounds")
    if net == 0:
        return []
    count, tail = divmod(net, preferred)
    if count > 10000:
        raise PlanningError("Scenario exceeds 10,000 batches per product/month")
    result = [preferred] * int(count)
    if tail:
        result.append(max(tail, minimum))
    return result


def seed_production_policies(session: Session) -> int:
    """Missing-key-only seed. Conflicts fail; caller owns atomic transaction."""
    inserted = 0
    resources = {}
    for code, name in (
        ("SYN-MIX", "Synthetic Mixing Line"),
        ("SYN-FILL", "Synthetic Finishing Line"),
    ):
        row = session.scalar(select(m.ProductionResource).where(m.ProductionResource.code == code))
        if row is None:
            row = m.ProductionResource(
                code=code,
                name=name,
                monthly_hours=Decimal(10),
                source_system=SOURCE,
                source_record_id=code,
            )
            session.add(row)
            session.flush()
            inserted += 1
        elif row.name != name or row.monthly_hours != 10:
            raise PlanningError("Synthetic resource seed conflicts with existing configuration")
        resources[code] = row.id
    for index in range(1, 5):
        product = session.scalar(select(m.Product).where(m.Product.code == f"SYN-FG-{index:03}"))
        if product is None or product.unit_of_measure != "kg":
            raise PlanningError("Four synthetic kg products are required before policy seeding")
        values = dict(
            product_id=product.id,
            resource_id=resources["SYN-MIX" if index <= 2 else "SYN-FILL"],
            unit_of_measure="kg",
            minimum_batch=Decimal(200),
            preferred_batch=Decimal(1000),
            maximum_batch=Decimal(1200),
            units_per_hour=Decimal(100),
            priority=index,
        )
        row = session.scalar(
            select(m.ProductionPolicy).where(m.ProductionPolicy.product_id == product.id)
        )
        if row is None:
            session.add(
                m.ProductionPolicy(**values, source_system=SOURCE, source_record_id=product.code)
            )
            inserted += 1
        elif any(getattr(row, key) != value for key, value in values.items()):
            raise PlanningError(
                "Synthetic production policy seed conflicts with existing configuration"
            )
    session.flush()
    return inserted


def forecast_demands(session: Session, code: str) -> list[Demand]:
    run = session.scalar(select(m.ForecastRun).where(m.ForecastRun.code == code))
    if run is None:
        raise LookupError("Forecast run not found")
    verify_saved(session, run)
    return [
        Demand(
            product_id=f["product_id"],
            period_start=f["period_start"],
            quantity=f["quantity"],
            unit_of_measure=f["unit_of_measure"],
        )
        for f in run.report["forecasts"]
    ]


def calculate(
    session: Session, request: WhatIf | None = None, forecast_run_code: str | None = None
) -> tuple[PlanResult, dict]:
    if (request is None) == (forecast_run_code is None):
        raise PlanningError("Choose exactly one demand mode: manual or forecast")
    demands = (
        request.demands if request is not None else forecast_demands(session, forecast_run_code)
    )
    # Validate duplicate keys even when the source is a persisted forecast.
    demands = WhatIf(demands=demands).demands
    products = {p.id: p for p in session.scalars(select(m.Product))}
    policies = {p.product_id: p for p in session.scalars(select(m.ProductionPolicy))}
    resources = {r.id: r for r in session.scalars(select(m.ProductionResource))}
    stock = positions(session)
    if forecast_run_code is not None and any(
        p.required_quantity > 0 for p in stock if p.item_type == "product"
    ):
        raise PlanningError(
            "Outstanding confirmed sales require governed forecast consumption; "
            "refusing to double-count firm and forecast demand"
        )
    fg = {p.item_id: max(p.projected_quantity, ZERO) for p in stock if p.item_type == "product"}
    raw = {
        p.item_id: max(p.projected_quantity, ZERO) for p in stock if p.item_type == "raw_material"
    }
    for demand in demands:
        if demand.product_id not in products:
            raise LookupError("Product not found")
        policy = policies.get(demand.product_id)
        if policy is None:
            raise PlanningError("Missing production policy for requested product")
        if not (
            demand.unit_of_measure
            == policy.unit_of_measure
            == products[demand.product_id].unit_of_measure
        ):
            raise PlanningError("Demand, policy and product units must match")
    ordered = sorted(
        demands,
        key=lambda d: (
            d.period_start,
            policies[d.product_id].priority,
            products[d.product_id].code,
        ),
    )
    payload = dict(
        algorithm_version=VERSION,
        demand_mode="manual" if request else "forecast",
        forecast_run_code=forecast_run_code,
        demands=[d.model_dump(mode="json") for d in ordered],
        positions=[p.model_dump(mode="json") for p in stock],
        policies=[],
        resources=[],
        boms=[],
    )
    for pid in sorted({d.product_id for d in demands}):
        p = policies[pid]
        payload["policies"].append(
            {
                k: str(getattr(p, k))
                for k in (
                    "product_id",
                    "resource_id",
                    "unit_of_measure",
                    "minimum_batch",
                    "preferred_batch",
                    "maximum_batch",
                    "units_per_hour",
                    "priority",
                )
            }
        )
    for rid in sorted({policies[d.product_id].resource_id for d in demands}):
        r = resources[rid]
        payload["resources"].append(dict(id=r.id, code=r.code, monthly_hours=str(r.monthly_hours)))
    remaining_hours, capacity = {}, {}
    surplus = {pid: ZERO for pid in fg}
    lines = []
    for rank, demand in enumerate(ordered, 1):
        pid = demand.product_id
        product, policy = products[pid], policies[pid]
        resource = resources[policy.resource_id]
        key = (demand.period_start, resource.id)
        if key not in capacity:
            remaining_hours[key] = resource.monthly_hours
            capacity[key] = CapacityResult(
                resource_id=resource.id,
                resource_code=resource.code,
                period_start=demand.period_start,
                required_hours=ZERO,
                available_hours=resource.monthly_hours,
                allocated_hours=ZERO,
                overload_hours=ZERO,
                utilisation_pct=None,
                feasible=True,
            )
        offset = min(demand.quantity, fg[pid])
        fg[pid] -= offset
        extra = min(demand.quantity - offset, surplus[pid])
        surplus[pid] -= extra
        net = demand.quantity - offset - extra
        sizes = batch_sizes(net, policy.minimum_batch, policy.preferred_batch, policy.maximum_batch)
        proposed = sum(sizes, ZERO)
        material_rows, bom_id, components = [], None, []
        if proposed:
            # Reuse Phase 4's active-BOM selection and stock validation, and its Decimal explosion.
            basis = scenario(
                session,
                ScenarioQuery(
                    product_id=pid, quantity=proposed, unit_of_measure=demand.unit_of_measure
                ),
            )
            bom_id = basis.bom_id
            bom = session.get(m.BillOfMaterial, bom_id)
            components = list(
                session.scalars(
                    select(m.BillOfMaterialLine)
                    .where(m.BillOfMaterialLine.bom_id == bom_id)
                    .order_by(m.BillOfMaterialLine.raw_material_id)
                )
            )
            payload["boms"].append(
                dict(
                    product_id=pid,
                    period_start=str(demand.period_start),
                    bom_id=bom_id,
                    output_quantity=str(bom.output_quantity),
                    lines=[
                        dict(raw_material_id=c.raw_material_id, quantity=str(c.quantity))
                        for c in components
                    ],
                )
            )
            # Sum batch-level explosions: rounding is applied once per physical proposed batch.
            for component, info in zip(components, basis.materials, strict=True):
                need = sum(
                    (explode(q, bom.output_quantity, component.quantity) for q in sizes), ZERO
                )
                available = raw[component.raw_material_id]
                material_rows.append(
                    MaterialNeed(
                        raw_material_id=component.raw_material_id,
                        material_code=info.material_code,
                        unit_of_measure=info.unit_of_measure,
                        required_quantity=need,
                        available_quantity=available,
                        shortage_quantity=max(need - available, ZERO),
                        allocated_quantity=ZERO,
                        remaining_quantity=available,
                    )
                )
        required = sum((hours(q, policy.units_per_hour) for q in sizes), ZERO)
        available_hours = remaining_hours[key]
        material_blocked = any(r.shortage_quantity > 0 for r in material_rows)
        capacity_blocked = required > available_hours
        batches, allocated, allocated_hours = [], ZERO, ZERO
        for sequence, quantity in enumerate(sizes, 1):
            duration = hours(quantity, policy.units_per_hour)
            needs = {
                c.raw_material_id: explode(quantity, bom.output_quantity, c.quantity)
                for c in components
            }
            lacks_material = any(raw[mid] < need for mid, need in needs.items())
            lacks_capacity = duration > remaining_hours[key]
            accepted = not (lacks_material or lacks_capacity)
            if accepted:
                remaining_hours[key] -= duration
                allocated += quantity
                allocated_hours += duration
                for mid, need in needs.items():
                    raw[mid] -= need
                    next(
                        r for r in material_rows if r.raw_material_id == mid
                    ).allocated_quantity += need
            reason = (
                "Allocated whole batch"
                if accepted
                else "Unallocated: "
                + ", ".join(
                    label
                    for flag, label in (
                        (lacks_material, "insufficient shared material"),
                        (lacks_capacity, "insufficient residual capacity"),
                    )
                    if flag
                )
            )
            batches.append(
                ProposedBatch(
                    sequence=sequence,
                    quantity=quantity,
                    hours=duration,
                    allocated=accepted,
                    explanation=reason,
                )
            )
        for row in material_rows:
            row.remaining_quantity = raw[row.raw_material_id]
        surplus[pid] += max(allocated - net, ZERO)
        status = (
            "MATERIAL_AND_CAPACITY_CONSTRAINED"
            if material_blocked and capacity_blocked
            else "MATERIAL_CONSTRAINED"
            if material_blocked
            else "CAPACITY_CONSTRAINED"
            if capacity_blocked
            else "FEASIBLE"
        )
        shortage_text = "; ".join(
            f"{r.material_code} short {r.shortage_quantity} {r.unit_of_measure}"
            for r in material_rows
            if r.shortage_quantity
        )
        explanation = (
            f"{demand.period_start:%Y-%m} {product.code}: gross {demand.quantity}, "
            f"stock offset {offset}, carried surplus {extra}, net {net} {demand.unit_of_measure}; "
            f"{len(batches)} proposed batches, {required} hours, {available_hours} hours remaining "
            f"at rank {rank} (period, priority {policy.priority}, product code). "
            f"Allocated {allocated}; unmet {max(net - allocated, ZERO)}. {status}. "
            + (shortage_text or "Materials sufficient.")
            + (
                f" Capacity short {required - available_hours} hours."
                if capacity_blocked
                else " Capacity sufficient."
            )
        )
        lines.append(
            PlanLine(
                product_id=pid,
                product_code=product.code,
                period_start=demand.period_start,
                unit_of_measure=demand.unit_of_measure,
                resource_id=resource.id,
                resource_code=resource.code,
                priority=policy.priority,
                allocation_rank=rank,
                bom_id=bom_id,
                gross_demand=demand.quantity,
                inventory_offset=offset,
                surplus_offset=extra,
                net_requirement=net,
                proposed_quantity=proposed,
                allocated_quantity=allocated,
                unmet_quantity=max(net - allocated, ZERO),
                batch_count=len(batches),
                batches=batches,
                materials=material_rows,
                required_hours=required,
                available_hours=available_hours,
                allocated_hours=allocated_hours,
                overload_hours=max(required - available_hours, ZERO),
                utilisation_pct=utilisation(required, available_hours),
                status=status,
                explanation=explanation,
            )
        )
        cap = capacity[key]
        cap.required_hours += required
        cap.allocated_hours += allocated_hours
        cap.overload_hours = max(cap.required_hours - cap.available_hours, ZERO)
        cap.utilisation_pct = utilisation(cap.required_hours, cap.available_hours)
        cap.feasible = cap.overload_hours == 0
    code = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    result = PlanResult(
        calculation_code=code,
        algorithm_version=VERSION,
        demand_mode=payload["demand_mode"],
        forecast_run_code=forecast_run_code,
        lines=lines,
        capacity=[capacity[k] for k in sorted(capacity)],
        explanations=EXPLANATIONS,
    )
    return result, payload


def save_forecast_plan(
    session: Session, forecast_run_code: str
) -> tuple[m.ProductionPlanRun, bool]:
    result, inputs = calculate(session, forecast_run_code=forecast_run_code)
    code = result.calculation_code
    existing = session.scalar(select(m.ProductionPlanRun).where(m.ProductionPlanRun.code == code))
    report = result.model_dump(mode="json")
    if existing is not None:
        if existing.inputs != inputs or existing.report != report:
            raise PlanningError("Saved production plan conflicts with deterministic evidence")
        for model, values in (
            (m.ProductionPlanLine, result.lines),
            (m.ProductionCapacityResult, result.capacity),
        ):
            saved = list(
                session.scalars(
                    select(model).where(model.plan_run_id == existing.id).order_by(model.id)
                )
            )
            if len(saved) != len(values):
                raise PlanningError("Saved production reporting evidence is incomplete")
            for row, value in zip(saved, values, strict=True):
                if any(
                    getattr(row, key) != item
                    for key, item in value.model_dump().items()
                    if key in model.__table__.columns
                ):
                    raise PlanningError("Saved production reporting evidence conflicts")
        saved_materials = list(
            session.scalars(
                select(m.ProductionMaterialResult)
                .join(
                    m.ProductionPlanLine,
                    m.ProductionMaterialResult.plan_line_id == m.ProductionPlanLine.id,
                )
                .where(m.ProductionPlanLine.plan_run_id == existing.id)
                .order_by(m.ProductionMaterialResult.id)
            )
        )
        expected_materials = [material for line in result.lines for material in line.materials]
        if len(saved_materials) != len(expected_materials) or any(
            any(getattr(saved, k) != v for k, v in expected.model_dump().items())
            for saved, expected in zip(saved_materials, expected_materials, strict=True)
        ):
            raise PlanningError("Saved material reporting evidence conflicts")
        return existing, False
    forecast = session.scalar(select(m.ForecastRun).where(m.ForecastRun.code == forecast_run_code))
    run = m.ProductionPlanRun(
        code=code,
        algorithm_version=VERSION,
        forecast_run_id=forecast.id,
        generated_at=datetime.now(UTC),
        inputs=inputs,
        report=report,
        source_system=SOURCE,
        source_record_id=code,
    )
    session.add(run)
    session.flush()
    for model, values in (
        (m.ProductionPlanLine, result.lines),
        (m.ProductionCapacityResult, result.capacity),
    ):
        for index, value in enumerate(values):
            fields = {k: v for k, v in value.model_dump().items() if k in model.__table__.columns}
            session.add(
                model(
                    **fields,
                    plan_run_id=run.id,
                    source_system=SOURCE,
                    source_record_id=f"{code}:{index}",
                )
            )
    session.flush()
    saved_lines = list(
        session.scalars(
            select(m.ProductionPlanLine)
            .where(m.ProductionPlanLine.plan_run_id == run.id)
            .order_by(m.ProductionPlanLine.id)
        )
    )
    for line, value in zip(saved_lines, result.lines, strict=True):
        for material in value.materials:
            session.add(
                m.ProductionMaterialResult(
                    **material.model_dump(),
                    plan_line_id=line.id,
                    source_system=SOURCE,
                    source_record_id=f"{code}:{line.product_id}:"
                    f"{line.period_start}:{material.raw_material_id}",
                )
            )
    session.flush()
    return run, True
