"""Archived demand, immutable evaluation runs and shared forecasting views."""

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0005_forecasting"
down_revision = "0004_fractional_bom"
branch_labels = None
depends_on = None


def upgrade():
    for filename in ("0005_tables.sql", "0005_forecasting.sql"):
        for statement in (
            Path(__file__).with_name(filename).read_text(encoding="utf-8-sig").split(";")
        ):
            if statement.strip():
                op.execute(statement)


def downgrade():
    connection = op.get_bind()
    if connection.scalar(text("SELECT COUNT(*) FROM forecast_runs")) or connection.scalar(
        text("SELECT COUNT(*) FROM demand_observations")
    ):
        raise RuntimeError("Archive forecasting evidence explicitly before downgrade")
    for name in (
        "vw_forecast_backtest",
        "vw_demand_forecast",
        "vw_forecast_accuracy",
        "vw_demand_history",
    ):
        op.execute(f"DROP VIEW {name}")
    for name in ("forecast_backtests", "forecast_metrics", "forecast_runs", "demand_observations"):
        op.drop_table(name)
