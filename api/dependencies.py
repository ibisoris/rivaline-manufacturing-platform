"""Request-scoped reads; transactions are repeatable and read-only on PostgreSQL."""

from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.session import get_engine


def read_session() -> Iterator[Session]:
    try:
        with (
            get_engine()
            .connect()
            .execution_options(isolation_level="REPEATABLE READ") as connection
        ):
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                with Session(connection, autoflush=False) as session:
                    yield session
    except (SQLAlchemyError, ValueError):
        raise HTTPException(status_code=503, detail="Operational data is unavailable") from None
