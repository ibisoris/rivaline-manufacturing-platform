"""Read-only operational reporting views; no business rows or tables are modified."""

from pathlib import Path

from alembic import op

revision = "0002_reporting"
down_revision = "0001_phase1"
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    for name in (
        "vw_operations_quantities",
        "vw_operations_kpis",
        "vw_data_quality_summary",
        "vw_supplier_material_flow",
        "vw_quality_performance",
        "vw_production_performance",
        "vw_order_fulfilment",
        "vw_inventory_position",
    ):
        op.execute(f"DROP VIEW {name}")
