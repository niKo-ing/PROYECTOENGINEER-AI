"""Autenticación propia: hash de contraseñas con scrypt y tokens JWT HS256.

* ``hash_password``/``verify_password``: scrypt (biblioteca estándar) con sal aleatoria de 16 bytes; el formato guarda
  los parámetros para poder subirlos más adelante sin invalidar las cuentas existentes.
* ``issue_token``/``decode_local_token``: JWT firmado con ``AUTH_JWT_SECRET``, emisor ``todobarato`` y audiencia
  ``todobarato-app``. Un token de otro emisor (Supabase) lo valida ``app.core.security`` por su propio camino.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from functools import lru_cache

import jwt

from app.core.config import settings

log = logging.getLogger(__name__)

LOCAL_ISSUER = "todobarato"
LOCAL_AUDIENCE = "todobarato-app"
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(7 * 24 * 3600)))

# Parámetros de scrypt: n=2^14, r=8, p=1 (≈16 MB de memoria por intento, ~50 ms).
_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


@lru_cache(maxsize=1)
def jwt_secret() -> str:
    """Secreto de firma. En producción es obligatorio; en desarrollo, sin él, se genera uno por proceso (las sesiones
    se pierden al reiniciar, pero nunca se firma con un valor conocido)."""
    secret = os.getenv("AUTH_JWT_SECRET", "").strip()
    if secret:
        return secret
    if settings.app_env.lower() == "production":
        raise RuntimeError("AUTH_JWT_SECRET es obligatorio en producción")
    log.warning("AUTH_JWT_SECRET no está definido: se usa un secreto temporal (las sesiones no sobreviven a un reinicio)")
    return secrets.token_urlsafe(48)


def issue_token(user_id: str, email: str, display_name: str | None = None, *, now: float | None = None) -> tuple[str, int]:
    issued = int(now if now is not None else time.time())
    claims = {
        "iss": LOCAL_ISSUER,
        "aud": LOCAL_AUDIENCE,
        "sub": user_id,
        "email": email,
        "name": display_name or "",
        "iat": issued,
        "exp": issued + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(claims, jwt_secret(), algorithm="HS256"), TOKEN_TTL_SECONDS


def is_local_token(token: str) -> bool:
    try:
        return jwt.decode(token, options={"verify_signature": False}).get("iss") == LOCAL_ISSUER
    except jwt.InvalidTokenError:
        return False


def decode_local_token(token: str) -> dict:
    """Valida firma, emisor, audiencia y vencimiento. Levanta ``jwt.InvalidTokenError`` si algo no cuadra."""
    return jwt.decode(token, jwt_secret(), algorithms=["HS256"], audience=LOCAL_AUDIENCE, issuer=LOCAL_ISSUER)
