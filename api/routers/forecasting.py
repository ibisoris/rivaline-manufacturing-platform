"""Bound read queries over forecasting views; no training or writes in HTTP requests."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import Date, bindparam, text

from api.routers.operations import ReadSession
from api.schemas import forecasting as s
from api.schemas.operations import Page
from database.models import Product

router = APIRouter(
    prefix="/api/v1/forecasts",
    tags=["Forecasting"],
    responses={503: {"description": "Database unavailable"}},
)


def view_page(session, view: str, filters, product_id: int | None = None) -> dict:
    # View identifiers are fixed by routes; user values are always bound parameters.
    clauses, parameters = [], {}
    for key, value in filters.model_dump().items():
        if value is None or key in ("limit", "offset"):
            continue
        if key in ("date_from", "date_to"):
            clauses.append("period_start " + (">=" if key == "date_from" else "<=") + " :" + key)
        elif key == "scope":
            clauses.append("product_id IS " + ("NULL" if value == "overall" else "NOT NULL"))
            continue
        else:
            clauses.append(key + " = :" + key)
        parameters[key] = value
    if product_id is not None:
        clauses.append("product_id = :path_product")
        parameters["path_product"] = product_id
    where = " WHERE " + " AND ".join(clauses) if clauses else ""

    def typed_query(sql: str):
        return text(sql).bindparams(
            *[bindparam(key, type_=Date()) for key in ("date_from", "date_to") if key in parameters]
        )

    total = session.scalar(typed_query("SELECT count(*) FROM " + view + where), parameters)
    order = "dataset_code, product_id, period_start" if view == "vw_demand_history" else "id"
    rows = (
        session.execute(
            typed_query(
                "SELECT * FROM "
                + view
                + where
                + " ORDER BY "
                + order
                + " LIMIT :limit OFFSET :offset"
            ),
            dict(parameters, limit=filters.limit, offset=filters.offset),
        )
        .mappings()
        .all()
    )
    return dict(items=rows, total=total, limit=filters.limit, offset=filters.offset)


@router.get(
    "",
    response_model=Page[s.Forecast],
    summary="Read persisted product-month forecasts",
    description=(
        "All historical runs; filter run_code to select a vintage. Date bounds "
        "apply to period_start."
    ),
)
def forecasts(session: ReadSession, filters: Annotated[s.ForecastFilter, Query()]):
    return view_page(session, "vw_demand_forecast", filters)


@router.get(
    "/evaluation",
    response_model=Page[s.Accuracy],
    summary="All candidate metrics, validation and held-out test",
    description=(
        "MAE/RMSE use the listed unit; WAPE is percent or null for zero actual "
        "totals. Overall rows are unit-separated."
    ),
)
def evaluation(session: ReadSession, filters: Annotated[s.AccuracyFilter, Query()]):
    return view_page(session, "vw_forecast_accuracy", filters)


@router.get(
    "/history",
    response_model=Page[s.History],
    summary="Archived synthetic product-month demand",
    description=(
        "Separate evaluation dataset; do not add to operational sales totals. "
        "Missing months are not imputed."
    ),
)
def demand_history(session: ReadSession, filters: Annotated[s.HistoryFilter, Query()]):
    return view_page(session, "vw_demand_history", filters)


@router.get(
    "/{product_id}",
    response_model=Page[s.Forecast],
    summary="Forecast history for one product",
    responses={404: {"description": "Product not found"}},
)
def product_forecasts(
    product_id: Annotated[int, Path(ge=1)],
    session: ReadSession,
    filters: Annotated[s.ForecastFilter, Query()],
):
    if session.get(Product, product_id) is None:
        raise HTTPException(404, "Product not found")
    return view_page(session, "vw_demand_forecast", filters, product_id)
