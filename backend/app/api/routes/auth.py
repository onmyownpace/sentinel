"""Email/password sign-up, sign-in, and the current-user probe.

Sessions are HttpOnly cookies. There is no OAuth and no password-reset mail.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_user
from app.api.public_shell import reject_if_registration_disabled
from app.core.config import get_settings
from app.models.user import User
from app.services.passwords import hash_password, validate_password_plaintext, verify_password
from app.services.sessions import SESSION_COOKIE_NAME, create_session, revoke_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_DATABASE_ERRORS = (SQLAlchemyError, OSError, TimeoutError, ConnectionError)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthCredentials(BaseModel):
    email: str
    password: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "dev@sentinel.local", "password": "dev-password-change-me"}]
        }
    )

    @field_validator("email")
    @classmethod
    def email_must_look_valid(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned or len(cleaned) > 320 or not _EMAIL_RE.match(cleaned):
            raise ValueError("Enter a valid email address")
        return cleaned

    @field_validator("password")
    @classmethod
    def password_must_meet_minimum(cls, value: str) -> str:
        return validate_password_plaintext(value)


class UserResponse(BaseModel):
    id: UUID
    email: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("/register", status_code=201, response_model=UserResponse)
async def register(
    payload: AuthCredentials,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Create an account and set a session cookie."""
    reject_if_registration_disabled()
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await _rollback(session)
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        ) from exc
    except _DATABASE_ERRORS as exc:
        await _rollback(session)
        _raise_database_error(exc)

    await _issue_session_cookie(session, response, user)
    await _commit(session)
    await _refresh(session, user)
    logger.info("Registered user %s", user.id)
    return user


@router.post("/login", response_model=UserResponse)
async def login(
    payload: AuthCredentials,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Verify email/password and set a session cookie."""
    try:
        result = await session.execute(select(User).where(User.email == payload.email))
        user = result.scalar_one_or_none()
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    await _issue_session_cookie(session, response, user)
    await _commit(session)
    await _refresh(session, user)
    return user


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Clear the session cookie and delete the server-side session row."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        await revoke_session(session, raw)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(require_user)) -> User:
    """Return the signed-in user, or 401 when there is no session."""
    return user


async def _issue_session_cookie(
    session: AsyncSession,
    response: Response,
    user: User,
) -> None:
    settings = get_settings()
    _, raw = await create_session(session, user.id, ttl_days=settings.session_ttl_days)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw,
        httponly=True,
        samesite=settings.session_cookie_samesite,
        path="/",
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        secure=settings.environment.lower() == "production"
        or settings.session_cookie_samesite == "none",
    )


async def _commit(session: AsyncSession) -> None:
    try:
        await session.commit()
    except _DATABASE_ERRORS as exc:
        await _rollback(session)
        _raise_database_error(exc)


async def _refresh(session: AsyncSession, user: User) -> None:
    try:
        await session.refresh(user)
    except _DATABASE_ERRORS as exc:
        _raise_database_error(exc)


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception as exc:
        logger.warning("Auth session rollback failed (%s)", exc.__class__.__name__)


def _raise_database_error(exc: Exception) -> NoReturn:
    logger.warning("Auth request failed (%s)", exc.__class__.__name__)
    if isinstance(exc, ProgrammingError):
        raise HTTPException(
            status_code=503,
            detail="The database schema is not ready. Apply migrations and try again.",
        ) from exc
    raise HTTPException(status_code=503, detail="The database is unavailable.") from exc
