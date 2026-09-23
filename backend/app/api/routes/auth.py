"""Registration and login."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.models import User
from app.schemas import Credentials, Token, UserOut
from app.security import hash_password, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(body: Credentials, session: SessionDep) -> Token:
    settings = get_settings()
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El registro está cerrado")
    if settings.invite_code and body.invite_code != settings.invite_code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Código de invitación inválido")

    taken = await session.scalar(select(User).where(User.email == body.email))
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
    )
    session.add(user)
    await session.commit()
    return Token(access_token=issue_token(user.id))


@router.post("/login", response_model=Token)
async def login(body: Credentials, session: SessionDep) -> Token:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return Token(access_token=issue_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
