"""Unit-explicit monthly decision-support contracts; no execution commands."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.schemas.filters import Pagination

Status = Literal[
    "FEASIBLE", "MATERIAL_CONSTRAINED", "CAPACITY_CONSTRAINED", "MATERIAL_AND_CAPACITY_CONSTRAINED"
]


class Demand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(ge=1)
    period_start: date
    quantity: Decimal = Field(ge=0, le=1000000, decimal_places=6)
    unit_of_measure: str = Field(min_length=1, max_length=12)

    @field_validator("period_start")
    @classmethod
    def monthly(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("Use the first day of the planning month")
        return value


class WhatIf(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "demands": [
                    {
                        "product_id": 1,
                        "period_start": "2026-11-01",
                        "quantity": "5000",
                        "unit_of_measure": "kg",
                    }
                ]
            }
        },
    )
    demands: list[Demand] = Field(min_length=1, max_length=48)

    @model_validator(mode="after")
    def distinct(self):
        keys = [(r.product_id, r.period_start) for r in self.demands]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate product/month demand; aggregate explicitly first")
        if len({r.period_start for r in self.demands}) > 12:
            raise ValueError("At most twelve planning months per scenario")
        return self


class PlanFilter(Pagination):
    forecast_run_code: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]{64}$")
    product_id: int | None = Field(default=None, ge=1)
    period_start: date | None = None
    status: Status | None = None

    @field_validator("period_start")
    @classmethod
    def monthly(cls, value):
        return Demand.monthly(value) if value is not None else None


class MaterialNeed(BaseModel):
    raw_material_id: int
    material_code: str
    unit_of_measure: str
    required_quantity: Decimal
    available_quantity: Decimal
    shortage_quantity: Decimal
    allocated_quantity: Decimal
    remaining_quantity: Decimal


class ProposedBatch(BaseModel):
    sequence: int
    quantity: Decimal
    hours: Decimal
    allocated: bool
    explanation: str


class PlanLine(BaseModel):
    product_id: int
    product_code: str
    period_start: date
    unit_of_measure: str
    resource_id: int
    resource_code: str
    priority: int
    allocation_rank: int
    bom_id: int | None
    gross_demand: Decimal
    inventory_offset: Decimal
    surplus_offset: Decimal
    net_requirement: Decimal
    proposed_quantity: Decimal
    allocated_quantity: Decimal
    unmet_quantity: Decimal
    batch_count: int
    batches: list[ProposedBatch]
    materials: list[MaterialNeed]
    required_hours: Decimal
    available_hours: Decimal
    allocated_hours: Decimal
    overload_hours: Decimal
    utilisation_pct: Decimal | None
    status: Status
    explanation: str


class CapacityResult(BaseModel):
    resource_id: int
    resource_code: str
    period_start: date
    required_hours: Decimal
    available_hours: Decimal
    allocated_hours: Decimal
    overload_hours: Decimal
    utilisation_pct: Decimal | None
    feasible: bool


class PlanResult(BaseModel):
    calculation_code: str
    algorithm_version: str
    demand_mode: Literal["manual", "forecast"]
    forecast_run_code: str | None
    persisted: bool = False
    lines: list[PlanLine]
    capacity: list[CapacityResult]
    explanations: list[str]


class PlanPage(BaseModel):
    calculation_code: str
    algorithm_version: str
    demand_mode: str
    forecast_run_code: str | None
    items: list[PlanLine]
    total: int
    limit: int
    offset: int
    explanations: list[str]
