"""Mensajería entre servicios: RabbitMQ (producción) con un respaldo en memoria (pruebas y desarrollo).

Cola durable + mensajes persistentes + ack manual: si el worker se cae a mitad de un mensaje, RabbitMQ lo reentrega.
Los mensajes que fallan ``MAX_ATTEMPTS`` veces van a la cola de «cartas muertas» (``<cola>.dlq``) para no bloquear la fila.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from collections.abc import Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)

MATCH_QUEUE = "match.requests"
MAX_ATTEMPTS = 3
Handler = Callable[[dict[str, Any]], None]


class Broker(Protocol):
    def publish(self, queue_name: str, message: dict[str, Any]) -> None: ...
    def consume_one(self, queue_name: str, handler: Handler) -> bool: ...
    def depth(self, queue_name: str) -> int: ...


class InMemoryBroker:
    def __init__(self) -> None:
        self._queues: dict[str, queue.Queue] = {}

    def _q(self, name: str) -> queue.Queue:
        return self._queues.setdefault(name, queue.Queue())

    def publish(self, queue_name, message):
        self._q(queue_name).put(json.loads(json.dumps(message)))

    def consume_one(self, queue_name, handler):
        try:
            message = self._q(queue_name).get_nowait()
        except queue.Empty:
            return False
        attempts = message.get("_attempts", 0) + 1
        try:
            handler(message)
        except Exception:  # noqa: BLE001 — el worker no debe caerse por un mensaje malo
            log.exception("Falló el mensaje (intento %s)", attempts)
            if attempts >= MAX_ATTEMPTS:
                self._q(f"{queue_name}.dlq").put(message)
            else:
                self._q(queue_name).put({**message, "_attempts": attempts})
        return True

    def depth(self, queue_name):
        return self._q(queue_name).qsize()


class RabbitBroker:
    """``pika.BlockingConnection`` NO es seguro entre hilos y FastAPI atiende en un pool de hilos: la prueba de carga
    con Locust mostró 11 % de errores 500 («StreamLostError … pop from an empty deque»). Se serializa todo acceso al
    canal con un candado y se reconecta una vez si la conexión se cayó."""

    def __init__(self, url: str | None = None):
        import pika

        self._pika = pika
        self.url = url or os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
        self._connection = None
        self._channel = None
        self._declared: set[str] = set()
        self._lock = threading.RLock()

    def _ch(self):
        if self._connection is None or self._connection.is_closed or self._channel is None or self._channel.is_closed:
            self._connection = self._pika.BlockingConnection(self._pika.URLParameters(self.url))
            self._channel = self._connection.channel()
            self._declared.clear()
        return self._channel

    def _declare(self, name: str) -> None:
        if name not in self._declared:
            self._ch().queue_declare(queue=f"{name}.dlq", durable=True)
            self._ch().queue_declare(queue=name, durable=True)
            self._declared.add(name)

    def _with_retry(self, operation):
        with self._lock:
            try:
                return operation()
            except (self._pika.exceptions.AMQPError, OSError):
                log.warning("Conexión con RabbitMQ perdida: reconectando")
                self._connection = self._channel = None
                return operation()

    def publish(self, queue_name, message):
        def op():
            self._declare(queue_name)
            self._ch().basic_publish(
                exchange="", routing_key=queue_name, body=json.dumps(message).encode(),
                properties=self._pika.BasicProperties(delivery_mode=2, content_type="application/json"),
            )

        self._with_retry(op)

    def consume_one(self, queue_name, handler):
        def fetch():
            self._declare(queue_name)
            return self._ch().basic_get(queue=queue_name, auto_ack=False)

        method, _properties, body = self._with_retry(fetch)
        if method is None:
            return False
        message = json.loads(body)
        attempts = message.get("_attempts", 0) + 1
        try:
            handler(message)  # fuera del candado: puede tardar (llama al modelo)
        except Exception:  # noqa: BLE001
            log.exception("Falló el mensaje (intento %s)", attempts)
            target = f"{queue_name}.dlq" if attempts >= MAX_ATTEMPTS else queue_name
            self._with_retry(lambda: self._ch().basic_publish("", target, json.dumps({**message, "_attempts": attempts}).encode(), self._pika.BasicProperties(delivery_mode=2)))
        self._with_retry(lambda: self._ch().basic_ack(method.delivery_tag))
        return True

    def depth(self, queue_name):
        def op():
            self._declare(queue_name)
            return self._ch().queue_declare(queue=queue_name, durable=True, passive=True).method.message_count

        return self._with_retry(op)


_broker: Broker | None = None


def get_broker() -> Broker:
    """RabbitMQ si hay ``RABBITMQ_URL``; si no, una cola en memoria (solo un proceso)."""
    global _broker
    if _broker is None:
        _broker = RabbitBroker() if os.getenv("RABBITMQ_URL") else InMemoryBroker()
    return _broker
