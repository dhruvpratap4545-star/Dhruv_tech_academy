"""Fixtures for tests that drive the real API against a real PostgreSQL.

Isolation strategy: each test runs inside an outer transaction on a single connection,
and the session the application uses is joined to it. The services still call ``commit()``
normally — those become savepoint releases — and the outer transaction is rolled back when
the test ends. Nothing is truncated between tests, so the suite stays fast as it grows.

The schema is built by running the real Alembic migration, not ``metadata.create_all``.
That way every test run also proves the migration produces the schema the models expect.

Skipped when no database is reachable, so unit tests still run on a laptop without one.
In CI a missing database is a failure instead, because silently skipping the entire
integration suite would make a red build look green.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.db import build_engine, get_db
from app.core.security import CSRF_HEADER, CSRF_HEADER_VALUE
from app.main import create_app
from app.modules.notifications import email as email_module
from app.modules.notifications.email import MemoryEmailProvider
from app.modules.rbac import catalog
from app.modules.rbac.context import context_cache

TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or settings.test_database_url
    or "postgresql+asyncpg://app:app@localhost:5433/app_test"
)
IN_CI = os.environ.get("CI", "").lower() == "true"


def _refuse_unless_disposable(url: str) -> None:
    """Refuse to wipe a database whose name does not say it is for tests.

    `_apply_migrations` drops the whole `public` schema. The URL it uses falls back to a
    hard-coded default, so running pytest on a machine where `TEST_DATABASE_URL` is unset
    but a database happens to sit on that host and port destroys it — every table, with no
    prompt and no way back. A developer's local `app` database is exactly that shape.

    The name is the only signal available before the drop, so the name has to carry the
    consent: a database called `app_test`, `dhruv_test` or `test` is one somebody created
    to be thrown away. Anything else stops the run with an explanation rather than a
    restore from backup.
    """
    from urllib.parse import urlsplit

    name = urlsplit(url).path.lstrip("/").split("?")[0]
    if name == "test" or name.endswith("_test") or name.startswith("test_"):
        return
    raise pytest.UsageError(
        f"Refusing to run: the integration tests erase every table in '{name}', and that "
        f"name does not mark it as a test database. Point TEST_DATABASE_URL at a database "
        f"named 'test', or ending in '_test', or starting with 'test_'."
    )


async def _database_reachable(url: str) -> str | None:
    engine = build_engine(url, pool_size=1, max_overflow=0)
    try:
        async with engine.connect():
            return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    _refuse_unless_disposable(TEST_DATABASE_URL)
    reason = await _database_reachable(TEST_DATABASE_URL)
    if reason is not None:
        message = (
            f"No test database at {TEST_DATABASE_URL} ({reason}). "
            "Start one with `docker compose up -d db_test`."
        )
        if IN_CI:
            pytest.fail(message)
        pytest.skip(message, allow_module_level=True)

    engine = build_engine(TEST_DATABASE_URL)
    await _apply_migrations(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _apply_migrations(engine) -> None:
    """Run Alembic against the test database, so the migration itself is under test."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    async with engine.begin() as conn:
        # A clean slate each session: the previous run's schema may predate a new migration.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))

    def _upgrade(connection) -> None:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    async with engine.begin() as conn:
        await conn.run_sync(_upgrade)


@pytest_asyncio.fixture
async def db_connection(db_engine) -> AsyncGenerator[AsyncConnection]:
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture
async def db(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession]:
    """A session joined to the test's outer transaction.

    ``join_transaction_mode="create_savepoint"`` is what makes application ``commit()``
    calls safe to roll back afterwards.
    """
    factory = async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def _clean_process_state() -> AsyncGenerator[None]:
    """The permission cache and the outbox are process-global; a leak between tests would
    make results depend on ordering."""
    context_cache.clear()
    provider = MemoryEmailProvider()
    email_module.set_provider(provider)
    yield
    context_cache.clear()


@pytest.fixture
def outbox() -> MemoryEmailProvider:
    provider = email_module.get_provider()
    assert isinstance(provider, MemoryEmailProvider)
    return provider


@pytest_asyncio.fixture
async def seeded(db: AsyncSession) -> AsyncSession:
    """Roles, permissions, the core module and the Direct institute."""
    from app.core import seed as seed_module

    await seed_module._seed_modules(db)
    await db.flush()
    permissions = await seed_module._seed_permissions(db)
    roles = await seed_module._seed_roles(db)
    await seed_module._seed_role_permissions(db, roles, permissions)
    await seed_module._seed_direct_institute(db)
    await db.commit()
    return db


@pytest_asyncio.fixture
async def client(db: AsyncSession, seeded: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """API client wired to the test's transaction-bound session."""
    app = create_app()

    async def _override() -> AsyncGenerator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={CSRF_HEADER: CSRF_HEADER_VALUE},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ------------------------------------------------------------------------- factories


@pytest_asyncio.fixture
async def make_user(db: AsyncSession, seeded: AsyncSession):
    """Create an active user holding one role at a scope."""
    from app.core.security import hash_password
    from app.modules.rbac import repository as rbac_repo
    from app.modules.rbac.models import UserRoleAssignment
    from app.modules.users.models import User, UserPreference

    async def _make(
        role_key: str,
        *,
        institute_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        email: str | None = None,
        password: str = "Jacaranda!Tide4",
        status: str = "active",
    ) -> User:
        user = User(
            email=email or f"{role_key}-{uuid.uuid4().hex[:8]}@example.com",
            full_name=role_key.replace("_", " ").title(),
            password_hash=hash_password(password) if status == "active" else None,
            status=status,
        )
        db.add(user)
        await db.flush()
        db.add(UserPreference(user_id=user.id))

        role = await rbac_repo.get_role_by_key(db, role_key)
        assert role is not None, f"role {role_key} is not seeded"
        db.add(
            UserRoleAssignment(
                user_id=user.id,
                role_id=role.id,
                institute_id=institute_id,
                branch_id=branch_id,
            )
        )
        await db.commit()
        context_cache.invalidate(user.id)
        return user

    return _make


@pytest_asyncio.fixture
async def login_as(client: AsyncClient):
    """Log a user in on the shared client and leave the cookies in place."""

    async def _login(email: str, password: str = "Jacaranda!Tide4") -> AsyncClient:
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        return client

    return _login


@pytest_asyncio.fixture
async def institute(db: AsyncSession, seeded: AsyncSession):
    """Create an institute with core enabled, plus an optional branch."""
    from app.modules.org.models import Branch, Institute
    from app.modules.rbac.models import InstituteModule

    async def _make(name: str, code: str, *, with_branch: str | None = None):
        row = Institute(name=name, code=code.upper(), type="college", status="active")
        db.add(row)
        await db.flush()
        db.add(InstituteModule(institute_id=row.id, module_key=catalog.CORE_MODULE, enabled=True))
        branch = None
        if with_branch:
            branch = Branch(institute_id=row.id, name=with_branch, code=with_branch.upper())
            db.add(branch)
            await db.flush()
        await db.commit()
        return row, branch

    return _make
