"""Тесты app/services/auth.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.services.auth import authenticate, create_user, issue_tokens, refresh_tokens


def make_user(
    user_id=None,
    email="u@test.ru",
    password="secret123",
    is_active=True,
    role=UserRole.MANAGER,
    contractor_id=None,
):
    from app.core.security import hash_password

    return User(
        id=user_id or uuid4(),
        email=email,
        full_name="Test",
        role=role,
        is_active=is_active,
        contractor_id=contractor_id,
        hashed_password=hash_password(password),
    )


def make_session_with_user(user):
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=user)
    return session


# ---------- authenticate ----------


@pytest.mark.asyncio
async def test_authenticate_success():
    user = make_user(password="secret123")
    session = make_session_with_user(user)
    result = await authenticate(session, "u@test.ru", "secret123")
    assert result.id == user.id
    assert user.last_login_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_authenticate_wrong_password():
    user = make_user(password="secret123")
    session = make_session_with_user(user)
    with pytest.raises(HTTPException) as exc:
        await authenticate(session, "u@test.ru", "wrong")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_unknown_user():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await authenticate(session, "nobody@test.ru", "secret")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_inactive_user():
    user = make_user(is_active=False)
    session = make_session_with_user(user)
    with pytest.raises(HTTPException) as exc:
        await authenticate(session, user.email, "secret123")
    assert exc.value.status_code == 403


# ---------- issue_tokens ----------


def test_issue_tokens_contains_both():
    user = make_user()
    tokens = issue_tokens(user)
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"
    assert tokens.expires_in > 0


def test_issue_tokens_role_in_access():
    user = make_user(role=UserRole.MANAGER)
    tokens = issue_tokens(user)
    # Декодируем access token
    from app.core.security import decode_token

    payload = decode_token(tokens.access_token)
    assert payload["role"] == "manager"


# ---------- refresh_tokens ----------


@pytest.mark.asyncio
async def test_refresh_tokens_success():
    user = make_user()
    refresh = create_access_token(user.id, extra={"type": "refresh"})
    # create_access_token добавляет type=access, нужно type=refresh
    from app.core.security import create_refresh_token

    refresh = create_refresh_token(user.id)
    session = make_session_with_user(user)
    tokens = await refresh_tokens(session, refresh)
    assert tokens.access_token


@pytest.mark.asyncio
async def test_refresh_tokens_invalid():
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await refresh_tokens(session, "garbage")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_tokens_wrong_type():
    """Передаём access token вместо refresh."""
    user = make_user()
    access = create_access_token(user.id)
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await refresh_tokens(session, access)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_tokens_user_not_found():
    from app.core.security import create_refresh_token

    refresh = create_refresh_token(uuid4())
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await refresh_tokens(session, refresh)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_tokens_user_inactive():
    from app.core.security import create_refresh_token

    user = make_user(is_active=False)
    refresh = create_refresh_token(user.id)
    session = make_session_with_user(user)
    with pytest.raises(HTTPException) as exc:
        await refresh_tokens(session, refresh)
    assert exc.value.status_code == 401


# ---------- create_user ----------


@pytest.mark.asyncio
async def test_create_user():
    session = AsyncMock()

    async def refresh_side_effect(*args, **kwargs):
        user = args[0] if args else None
        if user and hasattr(user, "id") and not user.id:
            from uuid import uuid4

            user.id = uuid4()

    session.refresh = AsyncMock(side_effect=refresh_side_effect)
    session.add = MagicMock()

    user = await create_user(
        session,
        email="new@test.ru",
        password="secret123",
        full_name="New User",
        role=UserRole.MASTER,
    )
    assert user.email == "new@test.ru"
    assert user.hashed_password != "secret123"  # захеширован
    assert user.role == UserRole.MASTER
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_with_contractor():
    session = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    contractor_id = uuid4()
    user = await create_user(
        session,
        email="c@test.ru",
        password="secret123",
        full_name="C User",
        role=UserRole.CONTRACTOR,
        contractor_id=contractor_id,
        phone="+7999",
    )
    assert user.contractor_id == contractor_id
    assert user.phone == "+7999"
