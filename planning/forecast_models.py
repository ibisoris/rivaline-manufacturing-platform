"""Small exact-arithmetic monthly models and time-aware evaluation; no future features."""

from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

from planning.inventory import PlanningError

VERSION = "forecast-v1"
MODELS = ("naive", "moving_average", "linear_trend")
HORIZON = 3
PRECISION = Decimal("0.000001")


class ForecastError(PlanningError):
    """Invalid/incomplete forecasting inputs; safe to report to a local API client."""


def month_add(start: date, offset: int) -> date:
    total = start.year * 12 + start.month - 1 + offset
    return date(total // 12, total % 12 + 1, 1)


def month_end(start: date) -> date:
    return start.replace(day=monthrange(start.year, start.month)[1])


def rounded(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)


def predict(history: list[Decimal], model: str, horizon: int = HORIZON) -> list[Decimal]:
    if len(history) < 3 or any(not v.is_finite() or v < 0 for v in history):
        raise ForecastError("At least three non-negative finite observations are required")
    if model not in MODELS or horizon < 1 or horizon > HORIZON:
        raise ForecastError("Unsupported model or horizon")
    with localcontext() as context:
        context.prec = 40
        if model == "naive":
            values = [history[-1]] * horizon
        elif model == "moving_average":
            values = [sum(history[-3:]) / Decimal(3)] * horizon
        else:
            n = Decimal(len(history))
            x = [Decimal(i) for i in range(len(history))]
            mean_x, mean_y = sum(x) / n, sum(history) / n
            slope = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, history, strict=True)) / sum(
                (a - mean_x) ** 2 for a in x
            )
            intercept = mean_y - slope * mean_x
            values = [intercept + slope * Decimal(len(history) + step) for step in range(horizon)]
        return [rounded(max(Decimal(0), v)) for v in values]


def metrics(actual: list[Decimal], predicted: list[Decimal]) -> dict:
    if not actual or len(actual) != len(predicted):
        raise ForecastError("Metrics require equally sized nonempty actual/predicted series")
    if any(not value.is_finite() or value < 0 for value in actual + predicted):
        raise ForecastError("Metric quantities must be finite and non-negative")
    with localcontext() as context:
        context.prec = 40
        errors = [abs(a - p) for a, p in zip(actual, predicted, strict=True)]
        denominator, count = sum(actual), Decimal(len(actual))
        return dict(
            observations=len(actual),
            mae=rounded(sum(errors) / count),
            rmse=rounded((sum(error**2 for error in errors) / count).sqrt()),
            wape_pct=rounded(100 * sum(errors) / denominator) if denominator else None,
        )


def select_model(validation: dict[str, dict]) -> str:
    """Lowest validation MAE; rounded-six-decimal ties favor the baseline, then simplicity."""
    return min(MODELS, key=lambda model: (validation[model]["mae"], MODELS.index(model)))


def evaluate(values: list[Decimal], periods: list[date]) -> dict:
    if len(values) != 24 or len(periods) != 24:
        raise ForecastError("This evaluation contract requires 24 complete monthly observations")
    if periods != [month_add(periods[0], i) for i in range(24)]:
        raise ForecastError("Missing or unordered months; no implicit zero filling is allowed")
    points, scores = [], {"validation": {}, "test": {}}
    for split, origins in (("validation", (12, 15, 18)), ("test", (21,))):
        for model in MODELS:
            actual, predicted = [], []
            for origin in origins:
                predictions = predict(values[:origin], model)
                actual.extend(values[origin : origin + HORIZON])
                predicted.extend(predictions)
                points.extend(
                    dict(
                        split=split,
                        model=model,
                        training_cutoff=str(month_end(periods[origin - 1])),
                        period_start=str(periods[origin + step]),
                        actual=str(values[origin + step]),
                        predicted=str(value),
                    )
                    for step, value in enumerate(predictions)
                )
            scores[split][model] = metrics(actual, predicted)
    selected = select_model(scores["validation"])
    return dict(
        selected_model=selected,
        metrics=scores,
        points=points,
        forecast=predict(values, selected),
        uncertainty="Historical validation MAE/RMSE only; no calibrated prediction interval",
    )
