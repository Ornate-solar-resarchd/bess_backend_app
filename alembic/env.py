from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.shared.base_model import Base

# Ensure model metadata is imported for autogenerate.
from app.domains.auth import models as auth_models  # noqa: F401
from app.domains.bess_unit import models as bess_models  # noqa: F401
from app.domains.commissioning import models as commissioning_models  # noqa: F401
from app.domains.engineer import models as engineer_models  # noqa: F401
from app.domains.installation import models as installation_models  # noqa: F401
from app.domains.master import models as master_models  # noqa: F401
from app.domains.rbac import models as rbac_models  # noqa: F401
from app.domains.shipment import models as shipment_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser used by Alembic treats `%` as interpolation syntax.
# Escape it to support URL-encoded passwords (e.g. `%21`).
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


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


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
