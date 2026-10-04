"""Validated, bounded query parameters. Unsupported parameters are rejected."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Pagination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MasterFilter(Pagination):
    active: bool | None = None


class Dated(Pagination):
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be later than date_to")
        return self


class InventoryFilter(Pagination):
    warehouse_id: int | None = Field(default=None, ge=1)
    product_id: int | None = Field(default=None, ge=1)
    raw_material_id: int | None = Field(default=None, ge=1)


class SalesFilter(Dated):
    status: Literal["open", "confirmed", "fulfilled", "cancelled"] | None = None
    customer_id: int | None = Field(default=None, ge=1)
    product_id: int | None = Field(default=None, ge=1)


class PurchaseFilter(Dated):
    status: Literal["open", "confirmed", "received", "cancelled"] | None = None
    supplier_id: int | None = Field(default=None, ge=1)


class ProductionFilter(Dated):
    status: Literal["planned", "released", "completed", "cancelled"] | None = None
    product_id: int | None = Field(default=None, ge=1)


class BatchFilter(Pagination):
    status: Literal["pending", "in_progress", "quarantined", "released", "rejected"] | None = None
    product_id: int | None = Field(default=None, ge=1)
    production_order_id: int | None = Field(default=None, ge=1)


class QualityFilter(Dated):
    result: Literal["pass", "fail", "pending"] | None = None
    production_batch_id: int | None = Field(default=None, ge=1)


class ShipmentFilter(Dated):
    status: Literal["pending", "dispatched", "delivered", "cancelled"] | None = None
    warehouse_id: int | None = Field(default=None, ge=1)


class EtlFilter(Dated):
    status: Literal["running", "succeeded", "failed"] | None = None


class IssueFilter(Dated):
    etl_run_id: int | None = Field(default=None, ge=1)
    severity: Literal["warning", "error"] | None = None
    status: Literal["open", "resolved", "accepted"] | None = None
    source_system: str | None = Field(default=None, min_length=1, max_length=80)
