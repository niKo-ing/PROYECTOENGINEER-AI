"""HTTP fetcher with safety limits for the Discovery Tool."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.ingestion.discovery.security import (
    _MAX_REDIRECTS,
    _MAX_RESPONSE_BYTES,
    _REQUEST_TIMEOUT,
    URLValidationError,
    validate_url,
)


@dataclass(frozen=True)
class FetchResult:
    html: str
    final_url: str
    http_status: int
    content_type: str


class HTTPFetcher:
    """Fetches a URL and returns sanitized HTML content with safety limits."""

    def fetch(self, url: str) -> FetchResult:
        validate_url(url)

        try:
            with httpx.Client(
                follow_redirects=True,
                max_redirects=_MAX_REDIRECTS,
                timeout=_REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "SoloTodo-Discovery/1.0",
                    "Accept": "text/html,application/xhtml+xml,*/*",
                },
            ) as client:
                response = client.get(url)
        except httpx.TimeoutException as exc:
            raise URLValidationError(f"Timeout al acceder a la URL: {exc}") from exc
        except httpx.ConnectError as exc:
            raise URLValidationError(f"Error de conexión: {exc}") from exc
        except httpx.TooManyRedirects as exc:
            raise URLValidationError(
                f"Demasiadas redirecciones (máximo {_MAX_REDIRECTS}): {exc}"
            ) from exc
        except httpx.UnsupportedProtocol as exc:
            raise URLValidationError(f"Protocolo no soportado: {exc}") from exc
        except Exception as exc:
            raise URLValidationError(f"Error inesperado al obtener la URL: {exc}") from exc

        content_type = response.headers.get("content-type", "")

        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise URLValidationError(
                f"Respuesta demasiado grande: {len(response.content)} bytes "
                f"(máximo {_MAX_RESPONSE_BYTES})"
            )

        html = response.text
        return FetchResult(
            html=html,
            final_url=str(response.url),
            http_status=response.status_code,
            content_type=content_type,
        )
