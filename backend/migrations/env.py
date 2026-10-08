"""Alembic environment. The URL comes from app settings, never from alembic.ini.

Three ways in, and all three end at the same ``_do_run_migrations``:

* ``alembic upgrade head``        - opens its own async engine
* ``alembic upgrade head --sql``  - offline, renders DDL without connecting
* the test suite                  - injects an existing connection through
  ``config.attributes["connection"]`` so migrations run inside the test's own event loop
  and transaction. Without that branch, Alembic would call ``asyncio.run`` from inside a
  loop that is already running.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.db import Base

# Importing every models module registers its tables on Base.metadata, which is what
# autogenerate diffs against. A module missing from this list silently drops out of
# migrations, so one line per module and no conditional imports.
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.org import models as org_models  # noqa: F401
from app.modules.rbac import models as rbac_models  # noqa: F401
from app.modules.users import models as users_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_do_run_migrations)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif (injected := config.attributes.get("connection")) is not None:
    # Already inside a running loop and an open transaction (the test suite).
    _do_run_migrations(injected)
else:
    asyncio.run(run_migrations_online())
