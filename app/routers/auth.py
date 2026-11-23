"""Registro e inicio de sesión con cuentas propias (reemplaza a Supabase Auth, cuyo proyecto ya no existe)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.local_auth import hash_password, issue_token, verify_password
from app.core.ratelimit import rate_limit
from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db
from app.models.account import UserAccount

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db)]
# 10 intentos por minuto e IP: frena la fuerza bruta sin molestar a una persona que se equivoca de clave.
limited = Depends(rate_limit("auth", "AUTH_RATE_LIMIT_PER_MINUTE", 10))
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def _valid_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL.match(value):
        raise ValueError("El correo no es válido")
    return value


EmailStr = Annotated[str, Field(min_length=5, max_length=254), AfterValidator(_valid_email)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("El nombre es demasiado corto")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccountRead(BaseModel):
    id: str
    email: str
    display_name: str | None


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AccountRead


def _session_for(account: UserAccount) -> SessionResponse:
    token, ttl = issue_token(account.id, account.email, account.display_name)
    return SessionResponse(access_token=token, expires_in=ttl, user=AccountRead(id=account.id, email=account.email, display_name=account.display_name))


def _find(db: Session, email: str) -> UserAccount | None:
    return db.scalar(select(UserAccount).where(func.lower(UserAccount.email) == email.strip().lower()))


@router.post("/register", response_model=SessionResponse, status_code=status.HTTP_201_CREATED, dependencies=[limited])
def register(payload: RegisterRequest, db: DbSession):
    email = payload.email.strip().lower()
    if _find(db, email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo")
    account = UserAccount(id=str(uuid.uuid4()), email=email, display_name=payload.display_name, password_hash=hash_password(payload.password), last_login_at=datetime.now(timezone.utc))
    db.add(account)
    db.commit()
    return _session_for(account)


@router.post("/login", response_model=SessionResponse, dependencies=[limited])
def login(payload: LoginRequest, db: DbSession):
    account = _find(db, payload.email)
    # Mismo mensaje si el correo no existe o la clave es incorrecta: no revela qué correos tienen cuenta.
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos")
    account.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return _session_for(account)


@router.get("/me", response_model=AccountRead)
def me(user: Annotated[AuthenticatedUser, Depends(get_current_user)], db: DbSession):
    account = db.get(UserAccount, user.id)
    if account is None:
        return AccountRead(id=user.id, email=user.email or "", display_name=None)
    return AccountRead(id=account.id, email=account.email, display_name=account.display_name)
