from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database.config import get_settings
from database.session import get_engine


def database_status() -> str:
    if not get_settings().postgres_password.get_secret_value():
        return "unconfigured"
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return "up"
    except SQLAlchemyError:
        # Do not expose connection strings, credentials or server exception text.
        return "down"
