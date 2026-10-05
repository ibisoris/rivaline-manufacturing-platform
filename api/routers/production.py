"""Computational production planning; even POST uses the read-only transaction."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from api.routers.operations import ReadSession
from api.schemas.operations import Page
from planning.production import calculate
from planning.production_contracts import CapacityResult, PlanFilter, PlanPage, PlanResult, WhatIf

router = APIRouter(
    prefix="/api/v1/planning",
    tags=["Production planning"],
    responses={
        404: {"description": "Unknown product/forecast run"},
        409: {"description": "Incomplete or conflicting planning inputs"},
    },
)


def compute(session, filters):
    try:
        result, _ = calculate(session, forecast_run_code=filters.forecast_run_code)
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    if filters.product_id is not None and not any(
        r.product_id == filters.product_id for r in result.lines
    ):
        raise HTTPException(404, "Product not present in forecast run")
    return result


def page(result, filters, constrained=False):
    rows = [
        r
        for r in result.lines
        if (filters.product_id is None or r.product_id == filters.product_id)
        and (filters.period_start is None or r.period_start == filters.period_start)
        and (filters.status is None or r.status == filters.status)
        and (not constrained or r.status != "FEASIBLE")
    ]
    return PlanPage(
        calculation_code=result.calculation_code,
        algorithm_version=result.algorithm_version,
        demand_mode=result.demand_mode,
        forecast_run_code=result.forecast_run_code,
        items=rows[filters.offset : filters.offset + filters.limit],
        total=len(rows),
        limit=filters.limit,
        offset=filters.offset,
        explanations=result.explanations,
    )


@router.get(
    "/production-plan",
    response_model=PlanPage,
    summary="Compute a proposed plan from one explicit forecast vintage",
    description="Calculates the complete horizon before filtering, preserving shared allocation. "
    "No records are written. Required forecast_run_code identifies the Phase 5 run.",
)
def production_plan(session: ReadSession, filters: Annotated[PlanFilter, Query()]):
    return page(compute(session, filters), filters)


@router.post(
    "/production-plan/what-if",
    response_model=PlanResult,
    summary="Compute additional manual demand without saving anything",
    description="Standalone alternative scenario, not added to a forecast. Supply canonical units "
    "and unique product/month entries. No orders, batches, purchases or plan runs saved.",
)
def what_if(session: ReadSession, request: WhatIf):
    try:
        return calculate(session, request=request)[0]
    except LookupError as error:
        raise HTTPException(404, str(error)) from None


@router.get(
    "/capacity",
    response_model=Page[CapacityResult],
    summary="Resource-month capacity for a complete forecast plan",
    description="Product/status filters select relevant resource-months; totals always retain "
    "all competing products. Available hours must never be summed from plan lines.",
)
def capacity(session: ReadSession, filters: Annotated[PlanFilter, Query()]):
    result = compute(session, filters)
    # Filter before pagination so capacity coverage is independent of line page size.
    keys = {
        (r.period_start, r.resource_id)
        for r in result.lines
        if (filters.product_id is None or r.product_id == filters.product_id)
        and (filters.period_start is None or r.period_start == filters.period_start)
        and (filters.status is None or r.status == filters.status)
    }
    rows = [r for r in result.capacity if (r.period_start, r.resource_id) in keys]
    return dict(
        items=rows[filters.offset : filters.offset + filters.limit],
        total=len(rows),
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get(
    "/constraints",
    response_model=PlanPage,
    summary="Explain material and capacity constraints in a forecast proposal",
)
def constraints(session: ReadSession, filters: Annotated[PlanFilter, Query()]):
    return page(compute(session, filters), filters, constrained=True)
