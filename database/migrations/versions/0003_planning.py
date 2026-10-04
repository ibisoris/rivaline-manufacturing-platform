"""Minimal synthetic planning policies and immutable calculation snapshots."""

from pathlib import Path

from alembic import op

revision = "0003_planning"
down_revision = "0002_reporting"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("0003_tables.sql", "0003_planning.sql"):
        for statement in Path(__file__).with_name(name).read_text(encoding="utf-8-sig").split(";"):
            if statement.strip():
                op.execute(statement)


def downgrade():
    from sqlalchemy import text

    connection = op.get_bind()
    if connection.scalar(text("SELECT COUNT(*) FROM planning_runs")):
        raise RuntimeError("Export and explicitly archive planning history before downgrade")
    for name in ("vw_reorder_recommendations", "vw_inventory_risk", "vw_material_requirements"):
        op.execute(f"DROP VIEW {name}")
    op.drop_table("planning_runs")
    op.drop_table("planning_policies")
