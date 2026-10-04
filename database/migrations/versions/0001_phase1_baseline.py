"""Frozen Phase 1 schema baseline; existing databases are verified before adoption."""

from pathlib import Path

from alembic import op

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).with_name("0001_phase1.sql").read_text(encoding="utf-8")
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError("Baseline downgrade is intentionally disabled to protect operational data")
