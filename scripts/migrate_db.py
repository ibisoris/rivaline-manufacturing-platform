"""Bootstrap a new DB or verify-and-stamp an existing unchanged Phase 1 database."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, MetaData, inspect

from database.models import PHASE1_TABLES, Base
from database.session import get_engine


def main():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with get_engine().begin() as connection:
        config.attributes["connection"] = connection
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "alembic_version" in tables:
            command.upgrade(config, "head")
            print("Migrations at head.")
        elif not tables:
            command.upgrade(config, "head")
            print("Frozen Phase 1 baseline created.")
        else:
            if tables != PHASE1_TABLES:
                raise RuntimeError(
                    "Existing database table set differs; refusing automatic adoption"
                )
            baseline = MetaData()
            for name in PHASE1_TABLES:
                Base.metadata.tables[name].to_metadata(baseline)
            differences = compare_metadata(MigrationContext.configure(connection), baseline)
            if differences:
                raise RuntimeError("Existing schema differs; review a migration before adoption")
            for name, table in baseline.tables.items():
                expected = {
                    connection.dialect.identifier_preparer.format_constraint(c)
                    for c in table.constraints
                    if isinstance(c, CheckConstraint)
                }
                if expected != {c["name"] for c in inspector.get_check_constraints(name)}:
                    raise RuntimeError("Check constraints differ; refusing adoption")
            command.stamp(config, "0001_phase1")
            command.upgrade(config, "head")
            print(
                "Existing Phase 1 schema verified, stamped and upgraded; business data preserved."
            )


if __name__ == "__main__":
    main()
