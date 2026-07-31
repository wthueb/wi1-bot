from alembic import context
from sqlalchemy import engine_from_config, pool

from wi1_bot.bot.db import get_db_path
from wi1_bot.bot.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# model metadata for 'autogenerate' support
target_metadata = Base.metadata

# Get database path using the shared utility function
db_path = get_db_path()

# Override the sqlalchemy.url with the actual database path
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
