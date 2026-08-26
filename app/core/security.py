from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


def unauthorized(detail: str = "Token de autenticación inválido") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


@lru_cache(maxsize=1)
def jwk_client() -> PyJWKClient:
    if not settings.supabase_url:
        raise unauthorized("Supabase Auth no está configurado")
    return PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


def validate_supabase_token(token: str) -> AuthenticatedUser:
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm == "HS256":
            if not settings.supabase_jwt_secret:
                raise unauthorized()
            key = settings.supabase_jwt_secret
        elif algorithm in {"RS256", "ES256"}:
            key = jwk_client().get_signing_key_from_jwt(token).key
        else:
            raise unauthorized()

        if not settings.supabase_url:
            raise unauthorized("Supabase Auth no está configurado")
        claims = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=settings.supabase_jwt_audience,
            issuer=f"{settings.supabase_url}/auth/v1",
        )
    except HTTPException:
        raise
    except InvalidTokenError as error:
        raise unauthorized() from error
    except Exception as error:
        raise unauthorized() from error

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise unauthorized()
    email = claims.get("email")
    return AuthenticatedUser(id=subject, email=email if isinstance(email, str) else None)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized("Se requiere un token Bearer")
    return validate_supabase_token(credentials.credentials)
