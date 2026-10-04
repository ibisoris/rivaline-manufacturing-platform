from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateSchema

from database.models import PHASE1_TABLES
from database.session import get_engine


def test_frozen_migration_has_all_tables():
    sql = Path("database/migrations/versions/0001_phase1.sql").read_text()
    for name in PHASE1_TABLES:
        assert f"CREATE TABLE {name} (" in sql


def test_baseline_executes_on_postgres(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Use --postgres for the live migration test")
    schema = "phase1_test_" + uuid4().hex
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(CreateSchema(schema))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0001_phase1")
            assert set(inspect(connection).get_table_names(schema=schema)) == set(PHASE1_TABLES) | {
                "alembic_version"
            }
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_phase1"
            )
        finally:
            transaction.rollback()
