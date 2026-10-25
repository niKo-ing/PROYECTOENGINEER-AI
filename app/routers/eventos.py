"""Eventos de AWS SNS para el worker de ingesta (arquitectura Event-Driven de la EP2).

EventBridge publica cada N horas un evento «ingesta_programada» en un tema SNS; SNS lo entrega por HTTP
al balanceador, que enruta ``/api/v1/eventos/*`` solo al worker. El endpoint:

- solo existe en el worker: requiere ``SNS_TOPIC_ARN_EVENTOS`` y el scheduler activo;
- verifica la firma de SNS (certificado de ``sns.<región>.amazonaws.com``) y que el tema sea el esperado;
- responde enseguida (202) y sincroniza las tiendas en segundo plano, sin solapar corridas.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

log = logging.getLogger(__name__)

router = APIRouter(prefix="/eventos", tags=["eventos"])

_HOST_SNS = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com$")
_CAMPOS_NOTIFICACION = ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type")
_CAMPOS_SUSCRIPCION = ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type")
_corriendo = threading.Lock()


def _tema_permitido() -> str:
    return os.getenv("SNS_TOPIC_ARN_EVENTOS", "").strip()


def _es_worker() -> bool:
    return os.getenv("INGESTION_SCHEDULER_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _url_de_sns(url: str) -> bool:
    partes = urlparse(url)
    return partes.scheme == "https" and bool(_HOST_SNS.match(partes.hostname or ""))


@lru_cache(maxsize=8)
def _certificado(url: str) -> x509.Certificate:
    respuesta = httpx.get(url, timeout=5)
    respuesta.raise_for_status()
    return x509.load_pem_x509_certificate(respuesta.content)


def _texto_a_firmar(mensaje: dict) -> bytes:
    campos = _CAMPOS_NOTIFICACION if mensaje.get("Type") == "Notification" else _CAMPOS_SUSCRIPCION
    return "".join(f"{campo}\n{mensaje[campo]}\n" for campo in campos if campo in mensaje).encode()


def firma_valida(mensaje: dict) -> bool:
    """Verifica la firma de un mensaje de SNS (SignatureVersion 1 = SHA1, 2 = SHA256)."""
    url_cert = mensaje.get("SigningCertURL", "")
    if not _url_de_sns(url_cert):
        return False
    algoritmo = {"1": hashes.SHA1(), "2": hashes.SHA256()}.get(str(mensaje.get("SignatureVersion")))
    if algoritmo is None:
        return False
    try:
        firma = base64.b64decode(mensaje["Signature"])
        _certificado(url_cert).public_key().verify(firma, _texto_a_firmar(mensaje), padding.PKCS1v15(), algoritmo)
        return True
    except (InvalidSignature, KeyError, ValueError, httpx.HTTPError):
        return False


def _sincronizar_tiendas() -> None:
    """Corre la sincronización de todas las tiendas activas. Si ya hay una corrida, no inicia otra."""
    if not _corriendo.acquire(blocking=False):
        log.info("Evento de ingesta ignorado: ya hay una sincronización en curso")
        return
    try:
        from sqlalchemy import select

        from app.db import SessionLocal
        from app.main import _run_store_sync
        from app.models.catalog import Store

        with SessionLocal() as db:
            tiendas = db.scalars(select(Store.id).where(Store.sync_enabled == True)).all()  # noqa: E712
        log.info("Evento de ingesta: sincronizando %d tiendas", len(tiendas))
        for tienda_id in tiendas:
            try:
                _run_store_sync(tienda_id)
            except Exception:  # noqa: BLE001 — una tienda caída no detiene a las demás
                log.exception("Falló la sincronización de la tienda %s", tienda_id)
    finally:
        _corriendo.release()


@router.post("/sns", status_code=202)
async def recibir_evento_sns(request: Request, tareas: BackgroundTasks) -> dict[str, str]:
    tema = _tema_permitido()
    if not tema or not _es_worker():
        raise HTTPException(status_code=404)
    try:
        # SNS manda JSON con Content-Type text/plain.
        mensaje = json.loads(await request.body())
    except ValueError:
        raise HTTPException(status_code=400, detail="Cuerpo inválido")
    if mensaje.get("TopicArn") != tema or not firma_valida(mensaje):
        log.warning("Evento SNS rechazado (tema %s)", mensaje.get("TopicArn"))
        raise HTTPException(status_code=403)

    tipo = mensaje.get("Type")
    if tipo == "SubscriptionConfirmation":
        url = mensaje.get("SubscribeURL", "")
        if not _url_de_sns(url):
            raise HTTPException(status_code=403)
        httpx.get(url, timeout=5).raise_for_status()
        log.info("Suscripción SNS confirmada para %s", tema)
        return {"estado": "suscripcion_confirmada"}
    if tipo == "Notification":
        tareas.add_task(_sincronizar_tiendas)
        return {"estado": "ingesta_encolada"}
    return {"estado": "ignorado"}
