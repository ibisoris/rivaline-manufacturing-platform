"""Fast SQLite tests, with explicit opt-in PostgreSQL constraint coverage."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from database.models import Base
from database.session import get_engine


def pytest_addoption(parser):
    parser.addoption(
        "--postgres",
        action="store_true",
        default=False,
        help="Also run relational tests against configured PostgreSQL in rolled-back schemas.",
    )


def pytest_generate_tests(metafunc):
    if "session" in metafunc.fixturenames:
        backends = (
            ["sqlite", "postgresql"] if metafunc.config.getoption("--postgres") else ["sqlite"]
        )
        metafunc.parametrize("session", backends, indirect=True)


@pytest.fixture
def session(request):
    if request.param == "postgresql":
        # DDL and test data stay inside an outer transaction. Tests may commit their
        # session savepoints, but cannot commit the outer schema/data transaction.
        engine = get_engine()
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                schema = "phase1_test_" + uuid4().hex
                connection.execute(CreateSchema(schema))
                connection = connection.execution_options(schema_translate_map={None: schema})
                Base.metadata.create_all(connection)
                with Session(connection, join_transaction_mode="create_savepoint") as session:
                    yield session
            finally:
                transaction.rollback()
        return

    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
