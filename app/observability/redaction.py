"""Enmascarado de datos personales antes de registrar o guardar texto (Ley 19.628 / 21.719: minimización)."""

from __future__ import annotations

import hashlib
import os
import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("correo", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("rut", re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b")),
    ("tarjeta", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("telefono", re.compile(r"(?:\+?56[ -]?)?\b9[ -]?\d{4}[ -]?\d{4}\b")),
    ("token", re.compile(r"\b(?:eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{30,}|sk-[A-Za-z0-9]{20,})\b")),
)


def redact(text: str | None) -> tuple[str, list[str]]:
    """Texto con los datos personales reemplazados por ``[correo]``, ``[rut]``… y la lista de tipos encontrados."""
    if not text:
        return "", []
    found: list[str] = []
    out = text
    for label, pattern in _PATTERNS:
        out, count = pattern.subn(f"[{label}]", out)
        if count:
            found.append(label)
    return out, found


def preview(text: str | None, limit: int = 200) -> str:
    clean, _ = redact(text)
    clean = " ".join(clean.split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def pseudonym(user_id: str | None) -> str | None:
    """Identificador estable pero no reversible del usuario para las métricas (sha256 con sal)."""
    if not user_id:
        return None
    salt = os.getenv("TRACE_SALT") or os.getenv("AUTH_JWT_SECRET") or "todobarato"
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:16]
