"""Auditable monthly forecasting use cases; no operational order/reorder writes."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models as m
from etl.demand_history import DATASET
from planning.contracts import ScenarioQuery
from planning.forecast_models import (
    HORIZON,
    MODELS,
    VERSION,
    ForecastError,
    evaluate,
    metrics,
    month_add,
    month_end,
)
from planning.inventory import scenario

SOURCE = "phase5_forecast_v1"


def json_values(value):
    return json.loads(json.dumps(value, default=lambda item: str(item)))


def history(
    session: Session, dataset: str, cutoff: date
) -> tuple[list[dict], dict[int, list[dict]]]:
    if cutoff != month_end(cutoff) or cutoff >= datetime.now(UTC).date().replace(day=1):
        raise ForecastError("Cutoff must be the end of a fully completed month")
    rows = list(
        session.scalars(
            select(m.DemandObservation)
            .where(
                m.DemandObservation.dataset_code == dataset,
                m.DemandObservation.period_start <= cutoff,
            )
            .order_by(
                m.DemandObservation.product_id,
                m.DemandObservation.period_start,
                m.DemandObservation.source_record_id,
            )
        )
    )
    if not rows:
        raise ForecastError("No demand observations for this dataset and cutoff")
    products = {p.id: p for p in session.scalars(select(m.Product))}
    sources, grouped = [], {}
    for row in rows:
        if (
            row.unit_of_measure != products[row.product_id].unit_of_measure
            or row.period_start.day != 1
        ):
            raise ForecastError("Archived unit or period conflicts with the product/month contract")
        sources.append(
            dict(
                product_id=row.product_id,
                product_code=products[row.product_id].code,
                period_start=str(row.period_start),
                quantity=format(row.quantity, ".6f"),
                unit_of_measure=row.unit_of_measure,
                file_sha256=row.file_sha256,
                source_record_id=row.source_record_id,
            )
        )
        key = (row.product_id, row.period_start)
        grouped[key] = grouped.get(key, Decimal(0)) + row.quantity
    series = {}
    for (product_id, period), quantity in sorted(grouped.items()):
        series.setdefault(product_id, []).append(
            dict(period=period, quantity=quantity, unit=products[product_id].unit_of_measure)
        )
    required = [month_add(cutoff.replace(day=1), offset) for offset in range(-23, 1)]
    for values in series.values():
        if [r["period"] for r in values] != required:
            raise ForecastError("Exactly 24 contiguous months ending at cutoff are required")
    # This version is explicitly a four-product demonstration; missing products cannot
    # vanish silently.
    if {products[pid].code for pid in series} != {f"SYN-FG-{i:03}" for i in range(1, 5)}:
        raise ForecastError("The synthetic dataset must include all four documented products")
    return sources, series


def verify_saved(session: Session, run: m.ForecastRun) -> None:
    rows = list(
        session.scalars(
            select(m.DemandForecast).where(
                m.DemandForecast.source_system == SOURCE,
                m.DemandForecast.source_record_id.like(run.code + ":%"),
            )
        )
    )
    expected = {
        (f["product_id"], date.fromisoformat(f["period_start"])): f for f in run.report["forecasts"]
    }
    if len(rows) != len(expected):
        raise ForecastError("Saved forecast evidence is incomplete; refusing silent replay repair")
    for row in rows:
        value = expected.get((row.product_id, row.period_start))
        if (
            value is None
            or row.quantity != Decimal(value["quantity"])
            or row.model_version != run.algorithm_version + ":" + value["selected_model"]
            or row.period_end != date.fromisoformat(value["period_end"])
        ):
            raise ForecastError("Saved forecast conflicts with immutable run evidence")
    saved = list(
        session.scalars(select(m.ForecastMetric).where(m.ForecastMetric.forecast_run_id == run.id))
    )
    expected_metrics = {
        (v["scope_key"], v["model_name"], v["evaluation_split"]): v for v in run.report["metrics"]
    }
    if len(saved) != len(expected_metrics):
        raise ForecastError("Saved metric evidence is incomplete")
    for row in saved:
        value = expected_metrics.get((row.scope_key, row.model_name, row.evaluation_split))
        if value is None or any(
            getattr(row, key) != (Decimal(value[key]) if value[key] is not None else None)
            for key in ("mae", "rmse", "wape_pct")
        ):
            raise ForecastError("Saved metric evidence conflicts with immutable run")

    points = list(
        session.scalars(
            select(m.ForecastBacktest).where(m.ForecastBacktest.forecast_run_id == run.id)
        )
    )
    expected_points = {
        (p["product_id"], p["model"], p["period_start"]): p for p in run.report["points"]
    }
    if len(points) != len(expected_points):
        raise ForecastError("Saved backtest evidence is incomplete")
    for point in points:
        value = expected_points.get((point.product_id, point.model_name, str(point.period_start)))
        if (
            value is None
            or point.actual_quantity != Decimal(value["actual"])
            or point.predicted_quantity != Decimal(value["predicted"])
            or str(point.training_cutoff) != value["training_cutoff"]
            or point.evaluation_split != value["split"]
            or point.unit_of_measure != value["unit_of_measure"]
        ):
            raise ForecastError("Saved backtest evidence conflicts with immutable run")


def generate_forecasts(
    session: Session, cutoff: date, dataset: str = DATASET
) -> tuple[m.ForecastRun, bool]:
    sources, series = history(session, dataset, cutoff)
    payload = dict(
        algorithm_version=VERSION,
        dataset_code=dataset,
        training_cutoff=str(cutoff),
        horizon=HORIZON,
        models=MODELS,
        validation_origins=(12, 15, 18),
        test_origin=21,
        sources=sources,
    )
    payload = json_values(payload)
    code = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = session.scalar(select(m.ForecastRun).where(m.ForecastRun.code == code))
    if previous:
        verify_saved(session, previous)
        return previous, False
    report = dict(metrics=[], points=[], forecasts=[], selected_models={})
    for product_id, values in series.items():
        result = evaluate([r["quantity"] for r in values], [r["period"] for r in values])
        unit = values[0]["unit"]
        selected = result["selected_model"]
        report["selected_models"][str(product_id)] = selected
        for split, models in result["metrics"].items():
            for model, score in models.items():
                report["metrics"].append(
                    dict(
                        product_id=product_id,
                        scope_key=f"product:{product_id}",
                        unit_of_measure=unit,
                        model_name=model,
                        evaluation_split=split,
                        **score,
                    )
                )
        report["points"].extend(
            dict(product_id=product_id, unit_of_measure=unit, **p) for p in result["points"]
        )
        for step, quantity in enumerate(result["forecast"], 1):
            period = month_add(cutoff, step)
            report["forecasts"].append(
                dict(
                    product_id=product_id,
                    unit_of_measure=unit,
                    period_start=str(period),
                    period_end=str(month_end(period)),
                    quantity=quantity,
                    selected_model=selected,
                )
            )
    for unit in sorted({r["unit_of_measure"] for r in report["points"]}):
        for split in ("validation", "test"):
            for model in MODELS:
                points = [
                    p
                    for p in report["points"]
                    if p["unit_of_measure"] == unit and p["split"] == split and p["model"] == model
                ]
                score = metrics(
                    [Decimal(p["actual"]) for p in points],
                    [Decimal(p["predicted"]) for p in points],
                )
                report["metrics"].append(
                    dict(
                        product_id=None,
                        scope_key="overall:" + unit,
                        unit_of_measure=unit,
                        model_name=model,
                        evaluation_split=split,
                        **score,
                    )
                )
    report = json_values(report)
    run = m.ForecastRun(
        code=code,
        dataset_code=dataset,
        algorithm_version=VERSION,
        training_cutoff=cutoff,
        horizon=HORIZON,
        generated_at=datetime.now(UTC),
        inputs=payload,
        report=report,
        source_system=SOURCE,
        source_record_id=code,
    )
    session.add(run)
    session.flush()
    for value in report["metrics"]:
        metric_values = dict(value)
        for key in ("mae", "rmse", "wape_pct"):
            metric_values[key] = Decimal(value[key]) if value[key] is not None else None
        session.add(
            m.ForecastMetric(
                forecast_run_id=run.id,
                **metric_values,
                source_system=SOURCE,
                source_record_id=f"{code}:{value['scope_key']}:{value['model_name']}:{value['evaluation_split']}",
            )
        )
    for value in report["points"]:
        session.add(
            m.ForecastBacktest(
                forecast_run_id=run.id,
                product_id=value["product_id"],
                unit_of_measure=value["unit_of_measure"],
                model_name=value["model"],
                evaluation_split=value["split"],
                training_cutoff=date.fromisoformat(value["training_cutoff"]),
                period_start=date.fromisoformat(value["period_start"]),
                actual_quantity=Decimal(value["actual"]),
                predicted_quantity=Decimal(value["predicted"]),
                source_system=SOURCE,
                source_record_id=f"{code}:{value['product_id']}:{value['model']}:{value['period_start']}",
            )
        )
    for value in report["forecasts"]:
        session.add(
            m.DemandForecast(
                product_id=value["product_id"],
                quantity=Decimal(value["quantity"]),
                period_start=date.fromisoformat(value["period_start"]),
                period_end=date.fromisoformat(value["period_end"]),
                model_version=VERSION + ":" + value["selected_model"],
                generated_at=run.generated_at,
                source_system=SOURCE,
                source_record_id=f"{code}:{value['product_id']}:{value['period_start']}",
            )
        )
    session.flush()
    return run, True


def forecast_to_bom(session: Session, run_code: str, product_id: int) -> dict:
    run = session.scalar(select(m.ForecastRun).where(m.ForecastRun.code == run_code))
    if run is None:
        raise LookupError("Forecast run not found")
    verify_saved(session, run)
    forecasts = [f for f in run.report["forecasts"] if f["product_id"] == product_id]
    if not forecasts:
        raise LookupError("Product forecast not found in this run")
    total = sum((Decimal(f["quantity"]) for f in forecasts), Decimal(0))
    if total == 0:
        raise ForecastError("Zero forecast requires no additional BOM demand")
    result = scenario(
        session,
        ScenarioQuery(
            product_id=product_id, quantity=total, unit_of_measure=forecasts[0]["unit_of_measure"]
        ),
    )
    return dict(
        run_code=run_code,
        forecast_periods=[f["period_start"] for f in forecasts],
        forecast_quantity=str(total),
        interpretation=(
            "Incremental what-if, not net firm demand; do not add overlapping orders twice"
        ),
        result=result.model_dump(mode="json"),
        persisted=False,
    )
