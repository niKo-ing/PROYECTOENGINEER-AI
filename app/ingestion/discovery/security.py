"""URL validation and SSRF prevention for the Discovery Tool."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 10
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
_REQUEST_TIMEOUT = 15.0


class URLValidationError(Exception):
    pass


def validate_url(url: str) -> urlparse:
    """Validate a URL is safe to fetch. Raises URLValidationError on failure."""
    if not url or not isinstance(url, str):
        raise URLValidationError("La URL no puede estar vacía")

    parsed = urlparse(url.strip())

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise URLValidationError(
            f"Esquema no permitido: {parsed.scheme!r}. Solo se permiten http/https."
        )

    if not parsed.hostname:
        raise URLValidationError("La URL no tiene un hostname válido")

    _check_host_not_private(parsed.hostname)

    return parsed


def _check_host_not_private(hostname: str) -> None:
    """Reject localhost, private IPs, link-local, and loopback addresses."""
    lower = hostname.lower()

    if lower in {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}:
        raise URLValidationError("No se permite acceder a localhost")

    try:
        addr = ipaddress.ip_address(lower)
    except ValueError:
        # It's a domain name, not an IP literal — check for .local, etc.
        if lower.endswith(".local") or lower.endswith(".internal"):
            raise URLValidationError(f"Dominio no permitido: {lower}")
        return

    if addr.is_loopback:
        raise URLValidationError(f"Dirección de loopback no permitida: {addr}")
    if addr.is_link_local:
        raise URLValidationError(f"Dirección link-local no permitida: {addr}")
    if addr.is_private:
        raise URLValidationError(f"Dirección privada no permitida: {addr}")
    if addr.is_reserved:
        raise URLValidationError(f"Dirección reservada no permitida: {addr}")
