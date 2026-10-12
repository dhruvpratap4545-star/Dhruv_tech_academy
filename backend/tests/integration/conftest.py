"""Fixtures for tests that drive the real API against a real MongoDB.

Isolation strategy: one throwaway database per test session, named ``test_dhruv_<random>``,
dropped at the end; every collection is emptied after each test (indexes stay, so uniqueness
is still tested). The name is generated here, never read from settings, so a run can never
touch the real database.

The application gets a fresh unit of work per request, exactly as in production. Test code
gets its own (``db``), which always reads from the database — so a test checking what a
request wrote sees the committed result, never a stale in-memory copy.

Point ``TEST_MONGODB_URL`` at a local MongoDB (``docker run -p 27018:27017 mongo:8.0``)
rather than Atlas: the suite makes thousands of round trips, and Atlas latency turns
minutes into the better part of an hour. Skipped when no database is reachable, except in
CI, where silently skipping the entire integration suite would make a red build look green.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from beanie import Document
from httpx import ASGITransport, AsyncClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core import db as db_module
from app.core.db import Db
from app.core.security import CSRF_HEADER, CSRF_HEADER_VALUE
from app.main import create_app
from app.modules.notifications import email as email_module
from app.modules.notifications.email import MemoryEmailProvider
from app.modules.rbac import catalog
from app.modules.rbac.context import context_cache

TEST_MONGODB_URL = os.environ.get("TEST_MONGODB_URL", "mongodb://localhost:27018")
IN_CI = os.environ.get("CI", "").lower() == "true"


class FreshDb(Db):
    """The test side's unit of work.

    Every read goes to the database and replaces whatever copy was held, and ``flush()``
    commits — tests set data up step by step and expect each step to be visible to the next
    query, the way a flushed session row was.
    """

    __slots__ = ()

    def track(self, doc):
        self._identity[(type(doc), doc.id)] = doc
        return doc

    async def get(self, model, doc_id):
        doc = await model.get(doc_id)
        return self.track(doc) if doc is not None else None

    async def flush(self) -> None:
        await self.commit()


@pytest_asyncio.fixture(scope="session")
async def mongo() -> AsyncGenerator[AsyncDatabase]:
    name = f"test_dhruv_{uuid.uuid4().hex[:8]}"
    try:
        database = await db_module.init_db(TEST_MONGODB_URL, name)
        await db_module.ping()
    except Exception as exc:
        message = (
            f"No test MongoDB at {TEST_MONGODB_URL} ({type(exc).__name__}). "
            "Start one with `docker run -d -p 27018:27017 mongo:8.0`."
        )
        if IN_CI:
            pytest.fail(message)
        pytest.skip(message, allow_module_level=True)

    yield database

    assert database.name.startswith("test_"), "refusing to drop a non-test database"
    await database.client.drop_database(name)
    await db_module.close_db()


@pytest_asyncio.fixture
async def db(mongo: AsyncDatabase) -> AsyncGenerator[Db]:
    yield FreshDb()
    for model in db_module.document_models():
        await model.get_pymongo_collection().delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def _clean_process_state() -> AsyncGenerator[None]:
    """The permission cache and the outbox are process-global; a leak between tests would
    make results depend on ordering."""
    from app.modules.rbac import service as rbac_service

    context_cache.clear()
    rbac_service._permission_modules.clear()
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
async def seeded(db: Db) -> Db:
    """Roles, permissions, the core module and the Direct institute."""
    from app.core import seed as seed_module

    await seed_module._seed_modules(db)
    await db.commit()
    permissions = await seed_module._seed_permissions(db)
    roles = await seed_module._seed_roles(db)
    await db.commit()
    await seed_module._seed_role_permissions(db, roles, permissions)
    await seed_module._seed_direct_institute(db)
    await db.commit()
    return db


@pytest_asyncio.fixture
async def client(db: Db, seeded: Db) -> AsyncGenerator[AsyncClient]:
    """API client against the app, which opens its own unit of work per request."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={CSRF_HEADER: CSRF_HEADER_VALUE},
    ) as ac:
        yield ac


# ------------------------------------------------------------------------- helpers


async def one(db: Db, model: type[Document], match: dict[str, Any] | None = None):
    """The first matching document, read fresh — the test-side ``scalar(select(...))``."""
    return await db.find_one(model, match or {})


async def all_of(db: Db, model: type[Document], match: dict[str, Any] | None = None):
    return await db.find(model, match or {})


# ------------------------------------------------------------------------- factories


@pytest_asyncio.fixture
async def make_user(db: Db, seeded: Db):
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
async def institute(db: Db, seeded: Db):
    """Create an institute with core enabled, plus an optional branch."""
    from app.modules.org.models import Branch, Institute
    from app.modules.rbac.models import InstituteModule

    async def _make(name: str, code: str, *, with_branch: str | None = None):
        row = Institute(name=name, code=code.upper(), type="college", status="active")
        db.add(row)
        db.add(InstituteModule(institute_id=row.id, module_key=catalog.CORE_MODULE, enabled=True))
        branch = None
        if with_branch:
            branch = Branch(institute_id=row.id, name=with_branch, code=with_branch.upper())
            db.add(branch)
        await db.commit()
        return row, branch

    return _make
