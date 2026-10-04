"""Read-only, versioned planning endpoints; writes require the explicit local CLI."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from api.routers.operations import ReadSession
from api.schemas.operations import Page
from planning import contracts as c
from planning.inventory import PlanningError, positions, recommendations, requirements, scenario

router = APIRouter(
    prefix="/api/v1",
    tags=["Inventory planning"],
    responses={
        409: {"description": "Incomplete planning inputs"},
        503: {"description": "Operational database unavailable"},
    },
)


def paginate(items: list, filters) -> dict:
    return dict(
        items=items[filters.offset : filters.offset + filters.limit],
        total=len(items),
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get(
    "/inventory/positions",
    response_model=Page[c.Position],
    summary="Pooled stock and explainable material reorder position",
    description="All warehouses pooled. "
    "Incoming assumes confirmed purchase lines wholly outstanding. "
    "Reservations and requirements are conservatively additive; no order allocation is inferred.",
)
def inventory_positions(session: ReadSession, filters: Annotated[c.PositionFilter, Query()]):
    rows = [
        p
        for p in positions(session)
        if (filters.item_type is None or p.item_type == filters.item_type)
        and (filters.item_id is None or p.item_id == filters.item_id)
        and (not filters.shortage_only or p.shortage_quantity > 0)
    ]
    return paginate(rows, filters)


@router.get(
    "/planning/material-requirements",
    response_model=Page[c.Requirement],
    summary="Outstanding BOM material needs for planned/released production",
)
def material_requirements(session: ReadSession, filters: Annotated[c.RequirementFilter, Query()]):
    rows = [
        r
        for r in requirements(session)
        if (filters.raw_material_id is None or r.raw_material_id == filters.raw_material_id)
        and (
            filters.production_order_id is None
            or r.production_order_id == filters.production_order_id
        )
    ]
    return paginate(rows, filters)


@router.get(
    "/planning/material-availability",
    response_model=c.ScenarioResult,
    summary="What-if additional production; no persistence",
    responses={
        404: {"description": "Unknown product"},
        409: {"description": "Missing/ambiguous BOM or unit conflict"},
    },
)
def material_availability(session: ReadSession, query: Annotated[c.ScenarioQuery, Query()]):
    try:
        return scenario(session, query)
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
    except PlanningError as error:
        raise HTTPException(409, str(error)) from None


@router.get(
    "/reorder-recommendations",
    response_model=Page[c.Recommendation],
    summary="Historical proposals with frozen inputs; proposals are not open supply",
)
def reorder_list(session: ReadSession, filters: Annotated[c.RecommendationFilter, Query()]):
    rows = [
        r
        for r in recommendations(session)
        if (filters.raw_material_id is None or r.raw_material_id == filters.raw_material_id)
        and (filters.warehouse_id is None or r.warehouse_id == filters.warehouse_id)
        and (filters.status is None or r.status == filters.status)
        and (filters.run_code is None or r.run_code == filters.run_code)
    ]
    return paginate(rows, filters)


@router.get(
    "/reorder-recommendations/{recommendation_id}",
    response_model=c.Recommendation,
    summary="One saved proposal and its calculation inputs",
    responses={404: {"description": "Unknown proposal"}},
)
def reorder_detail(recommendation_id: Annotated[int, Path(ge=1)], session: ReadSession):
    for row in recommendations(session):
        if row.id == recommendation_id:
            return row
    raise HTTPException(404, "Reorder recommendation not found")
