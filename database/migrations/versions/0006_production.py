"""Synthetic resources, production policies and immutable planning snapshots."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0006_production"
down_revision = "0005_forecasting"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("0006_tables.sql", "0006_production.sql"):
        for statement in Path(__file__).with_name(name).read_text(encoding="utf-8-sig").split(";"):
            if statement.strip():
                op.execute(statement)


def downgrade():
    if op.get_bind().scalar(text("SELECT COUNT(*) FROM production_plan_runs")):
        raise RuntimeError("Archive production planning evidence explicitly before downgrade")
    for name in (
        "vw_planning_materials",
        "vw_forecast_to_production",
        "vw_planning_constraints",
        "vw_capacity_utilisation",
        "vw_production_plan",
    ):
        op.execute(f"DROP VIEW {name}")
    for name in (
        "production_material_results",
        "production_capacity_results",
        "production_plan_lines",
        "production_plan_runs",
        "production_policies",
        "production_resources",
    ):
        op.drop_table(name)
