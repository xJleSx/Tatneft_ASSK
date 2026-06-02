"""Auth: логин, рефреш, /me, /seed (dev only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import login_limiter
from app.db.session import get_session
from app.mocks.generators.seed import run_all_seeds
from app.models.user import User
from app.schemas.user import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.services.auth import authenticate, issue_tokens, refresh_tokens

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    # Rate limit по IP. Не раскрываем существование пользователя через разный ответ.
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = login_limiter.check(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Слишком много попыток входа. Повторите через {retry_after} сек.",
            headers={"Retry-After": str(retry_after)},
        )
    user = await authenticate(session, body.email, body.password)
    return issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    return await refresh_tokens(session, body.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/seed", tags=["dev"], status_code=status.HTTP_201_CREATED)
async def seed(session: AsyncSession = Depends(get_session)) -> dict:
    """Заполнить БД синтетическими данными (только dev)."""
    if not (await _confirm_dev(session)):
        raise HTTPException(status_code=403, detail="Disabled outside dev")
    return await run_all_seeds(session)


async def _confirm_dev(session: AsyncSession) -> bool:
    from app.core.config import settings

    return settings.app_env == "dev"
