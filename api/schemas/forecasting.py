"""Explicit forecast response contracts and bounded, validated read filters."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api.schemas.filters import Dated, Pagination


class ForecastFilter(Dated):
    product_id: int | None = Field(default=None, ge=1)
    run_code: str | None = Field(default=None, min_length=64, max_length=64)
    model_version: str | None = Field(default=None, min_length=1, max_length=80)


class AccuracyFilter(Pagination):
    product_id: int | None = Field(default=None, ge=1)
    run_code: str | None = Field(default=None, min_length=64, max_length=64)
    model_name: Literal["naive", "moving_average", "linear_trend"] | None = None
    evaluation_split: Literal["validation", "test"] | None = None
    scope: Literal["product", "overall"] | None = None


class HistoryFilter(Dated):
    product_id: int | None = Field(default=None, ge=1)
    dataset_code: str | None = Field(default=None, min_length=1, max_length=60)


class UTCModel(BaseModel):
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def in_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Forecast(UTCModel):
    id: int
    product_id: int
    product_code: str
    period_start: date
    period_end: date
    quantity: Decimal
    unit_of_measure: str
    model_version: str
    selected_model: str
    run_code: str
    dataset_code: str
    training_cutoff: date
    horizon: int
    validation_mae: Decimal
    validation_rmse: Decimal
    uncertainty_method: str = (
        "Historical validation error scale; no prediction interval or coverage guarantee"
    )


class Accuracy(UTCModel):
    id: int
    run_code: str
    dataset_code: str
    training_cutoff: date
    algorithm_version: str
    product_id: int | None
    scope_key: str
    unit_of_measure: str
    model_name: str
    evaluation_split: str
    observations: int
    mae: Decimal
    rmse: Decimal
    wape_pct: Decimal | None


class History(BaseModel):
    dataset_code: str
    product_id: int
    product_code: str
    period_start: date
    unit_of_measure: str
    quantity: Decimal
    source_rows: int
