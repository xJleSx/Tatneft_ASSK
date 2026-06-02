"""Общие фикстуры и настройки для тестов."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

# Test env (must be set BEFORE importing app modules)
os.environ["APP_ENV"] = "dev"
os.environ["SECRET_KEY"] = "test-secret-key-for-jwt-only"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://test"
os.environ["ASUTP_MODE"] = "mock"
os.environ["MINIO_BUCKET"] = "askk-photos-test"
os.environ["GEO_RADIUS_M"] = "75"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Reset settings cache so test env vars take effect
from app.core.config import get_settings

get_settings.cache_clear()

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

# ---------- Settings ----------


@pytest.fixture(scope="session")
def settings():
    get_settings.cache_clear()
    return get_settings()


# ---------- Engine / Session ----------


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


# ---------- Users ----------


@pytest_asyncio.fixture
async def manager_user(db_session) -> User:
    user = User(
        id=uuid4(),
        email="manager@test.ru",
        full_name="Test Manager",
        role=UserRole.MANAGER,
        is_active=True,
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def contractor_user(db_session) -> User:
    user = User(
        id=uuid4(),
        email="contractor@test.ru",
        full_name="Test Contractor",
        role=UserRole.CONTRACTOR,
        is_active=True,
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session) -> User:
    user = User(
        id=uuid4(),
        email="admin@test.ru",
        full_name="Test Admin",
        role=UserRole.ADMIN,
        is_active=True,
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def master_user(db_session) -> User:
    user = User(
        id=uuid4(),
        email="master@test.ru",
        full_name="Test Master",
        role=UserRole.MASTER,
        is_active=True,
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def technologist_user(db_session) -> User:
    user = User(
        id=uuid4(),
        email="tech@test.ru",
        full_name="Test Technologist",
        role=UserRole.TECHNOLOGIST,
        is_active=True,
        hashed_password=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def make_token(user: User) -> str:
    return create_access_token(user.id, extra={"role": user.role.value})


@pytest.fixture
def manager_token(manager_user) -> str:
    return make_token(manager_user)


@pytest.fixture
def contractor_token(contractor_user) -> str:
    return make_token(contractor_user)


@pytest.fixture
def admin_token(admin_user) -> str:
    return make_token(admin_user)


@pytest.fixture
def master_token(master_user) -> str:
    return make_token(master_user)


@pytest.fixture
def technologist_token(technologist_user) -> str:
    return make_token(technologist_user)


# ---------- HTTP client ----------


@pytest_asyncio.fixture
async def client(db_session) -> AsyncIterator[AsyncClient]:
    """AsyncClient с подменой get_session на тестовую БД."""
    from app.db.session import get_session
    from app.main import app

    async def _get_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _get_session_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
