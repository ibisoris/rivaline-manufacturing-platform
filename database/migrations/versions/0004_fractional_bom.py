"""Preserve fractional BOM division on numeric-affinity SQLite test fixtures."""

from pathlib import Path

from alembic import op

revision = "0004_fractional_bom"
down_revision = "0003_planning"
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).with_suffix(".sql").read_text()
    op.execute(sql.replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1))


def downgrade():
    sql = Path(__file__).with_name("0003_planning.sql").read_text().split(";")[0]
    op.execute(sql.replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1))
