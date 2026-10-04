"""Use project configuration; never put credentials in alembic.ini."""

from alembic import context

from database.models import Base
from database.session import get_engine


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        migrate(supplied)
    else:
        with get_engine().connect() as connection:
            migrate(connection)
