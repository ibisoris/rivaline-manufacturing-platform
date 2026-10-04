"""Typed, unit-explicit planning contracts shared by calculations and HTTP."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.filters import Pagination


class Position(BaseModel):
    item_type: Literal["product", "raw_material"]
    item_id: int
    item_code: str
    unit_of_measure: str
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    required_quantity: Decimal
    incoming_quantity: Decimal
    projected_quantity: Decimal
    shortage_quantity: Decimal
    incomplete_bom_count: int
    policy_id: int | None
    destination_warehouse_id: int | None
    safety_stock: Decimal | None
    reorder_point: Decimal | None
    target_stock: Decimal | None
    minimum_order_quantity: Decimal | None
    recommended_quantity: Decimal | None
    risk_status: str
    explanation: str = ""


class Requirement(BaseModel):
    production_order_id: int
    production_order_code: str
    product_id: int
    sales_order_line_id: int | None
    bom_id: int
    production_status: str
    planned_quantity: Decimal
    output_quantity: Decimal
    bom_quantity: Decimal
    raw_material_id: int
    material_code: str
    unit_of_measure: str
    gross_quantity: Decimal
    consumed_quantity: Decimal
    required_quantity: Decimal


class PositionFilter(Pagination):
    item_type: Literal["product", "raw_material"] | None = None
    item_id: int | None = Field(default=None, ge=1)
    shortage_only: bool = False


class RequirementFilter(Pagination):
    raw_material_id: int | None = Field(default=None, ge=1)
    production_order_id: int | None = Field(default=None, ge=1)


class RecommendationFilter(Pagination):
    raw_material_id: int | None = Field(default=None, ge=1)
    warehouse_id: int | None = Field(default=None, ge=1)
    status: Literal["proposed", "accepted", "dismissed"] | None = None
    run_code: str | None = Field(default=None, min_length=64, max_length=64)


class ScenarioQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(ge=1)
    quantity: Decimal = Field(gt=0, le=Decimal("1000000000"), decimal_places=6)
    unit_of_measure: str = Field(min_length=1, max_length=12)
    bom_id: int | None = Field(default=None, ge=1)


class ScenarioMaterial(BaseModel):
    raw_material_id: int
    material_code: str
    unit_of_measure: str
    incremental_requirement: Decimal
    current_available: Decimal
    baseline_projected: Decimal
    scenario_projected: Decimal
    shortage_quantity: Decimal
    additional_shortage: Decimal
    recommended_quantity: Decimal | None
    affected_production_order_ids: list[int]
    explanation: str


class ScenarioResult(BaseModel):
    product_id: int
    bom_id: int
    quantity: Decimal
    unit_of_measure: str
    materials: list[ScenarioMaterial]
    persisted: bool = False


class Recommendation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    raw_material_id: int
    warehouse_id: int
    quantity: Decimal
    reason: str
    generated_at: datetime
    status: str
    run_code: str | None = None
    algorithm_version: str | None = None
    input_position: Position | None = None
    affected_requirements: list[Requirement] = []

    @field_validator("generated_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        # SQLite loses timezone information; persisted PostgreSQL timestamps are aware.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
