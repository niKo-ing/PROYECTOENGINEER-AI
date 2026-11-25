"""Trazador de ejecuciones de IA.

Uso::

    with RunTracer(db, flow="asistente_pc", user_id=user.id, user_text=mensaje) as trace:
        llm.invoke(mensajes, config={"callbacks": [trace.callback]})   # mide cada llamada y sus tokens
        with trace.stage("recomendador"):
            ...
        trace.set(status="ok", output_text=respuesta)

``TracingCallback`` es un ``BaseCallbackHandler`` de LangChain: LangGraph lo propaga a los nodos, al modelo y a las
herramientas, así una ejecución del agente queda completa (cada llamada a Gemini con su latencia y tokens, cada
herramienta con su duración y si falló). Al cerrar se escribe una línea JSON en el log ``todobarato.trace`` y la fila
en ``agent_runs``/``agent_spans`` con una sesión aparte: un fallo al guardar la traza nunca rompe la respuesta.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from sqlalchemy.orm import Session

from app.observability.redaction import preview, pseudonym, redact

log = logging.getLogger("todobarato.trace")
_file_lock = threading.Lock()


def _ensure_file_log() -> None:
    """Si ``TRACE_LOG_FILE`` está definido, cada ejecución se escribe como una línea JSON (JSONL, con rotación) que
    ``scripts/analizar_trazas.py`` o cualquier recolector de logs puede leer."""
    path = os.getenv("TRACE_LOG_FILE")
    if not path:
        return
    with _file_lock:
        if any(getattr(h, "todobarato_path", None) == path for h in log.handlers):
            return
        from logging.handlers import RotatingFileHandler

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.todobarato_path = path  # type: ignore[attr-defined]
        log.addHandler(handler)
        log.setLevel(logging.INFO)


def _usage(response: Any) -> tuple[int | None, int | None, str | None]:
    try:
        generation = response.generations[0][0]
        message = getattr(generation, "message", None)
        usage = getattr(message, "usage_metadata", None) or {}
        meta = getattr(message, "response_metadata", None) or {}
        model = meta.get("model_name") or meta.get("model")
        if usage:
            return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), model
        llm_usage = (response.llm_output or {}).get("token_usage") or {}
        if llm_usage:
            return int(llm_usage.get("prompt_tokens") or 0), int(llm_usage.get("completion_tokens") or 0), model
        return None, None, model
    except (AttributeError, IndexError, TypeError, ValueError):
        return None, None, None


class TracingCallback(BaseCallbackHandler):
    """Convierte los eventos de LangChain en tramos medidos."""

    raise_error = False

    def __init__(self, tracer: "RunTracer"):
        self.tracer = tracer
        self._open: dict[UUID, tuple[str, str, float, dict]] = {}
        self._lock = threading.Lock()

    def _start(self, run_id: UUID, kind: str, name: str, detail: dict | None = None) -> None:
        with self._lock:
            self._open[run_id] = (kind, name, time.perf_counter(), detail or {})

    def _end(self, run_id: UUID, status: str = "ok", **extra: Any) -> None:
        with self._lock:
            opened = self._open.pop(run_id, None)
        if opened is None:
            return
        kind, name, started, detail = opened
        self.tracer.add_span(kind, name, started, time.perf_counter(), status=status, detail={**detail, **{k: v for k, v in extra.items() if k not in ("input_tokens", "output_tokens")}},
                             input_tokens=extra.get("input_tokens"), output_tokens=extra.get("output_tokens"))

    # Modelo
    def on_chat_model_start(self, serialized: dict, messages: list, *, run_id: UUID, **kwargs: Any) -> None:
        name = (kwargs.get("metadata") or {}).get("ls_model_name") or (serialized or {}).get("name") or "llm"
        node = (kwargs.get("metadata") or {}).get("langgraph_node")
        self._start(run_id, "llm", str(name)[:80], {"node": node} if node else {})

    def on_llm_start(self, serialized: dict, prompts: list, *, run_id: UUID, **kwargs: Any) -> None:
        self._start(run_id, "llm", str((serialized or {}).get("name") or "llm")[:80])

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        tokens_in, tokens_out, model = _usage(response)
        if model:
            self.tracer.model = model
        self._end(run_id, input_tokens=tokens_in, output_tokens=tokens_out)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._end(run_id, status="error", error=type(error).__name__, message=redact(str(error))[0][:200])

    # Herramientas
    def on_tool_start(self, serialized: dict, input_str: str, *, run_id: UUID, **kwargs: Any) -> None:
        self._start(run_id, "tool", str((serialized or {}).get("name") or kwargs.get("name") or "tool")[:80], {"args": preview(input_str, 160)})

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        text = getattr(output, "content", output)
        status = "error" if getattr(output, "status", None) == "error" else "ok"
        self._end(run_id, status=status, output_chars=len(str(text or "")))

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._end(run_id, status="error", error=type(error).__name__, message=redact(str(error))[0][:200])


class RunTracer:
    def __init__(self, db: Session | None, *, flow: str, user_id: str | None = None, user_text: str = "", eval_tag: str | None = None, model: str | None = None):
        self.db = db
        self.flow = flow
        self.run_id = uuid.uuid4().hex
        self.user_hash = pseudonym(user_id)
        self.user_text = user_text or ""
        self.eval_tag = eval_tag
        self.model = model or os.getenv("GEMINI_MODEL")
        self.spans: list[dict[str, Any]] = []
        self.fields: dict[str, Any] = {"status": "ok", "guardrails": {}, "quality": {}, "extra": {}}
        self.callback = TracingCallback(self)
        self._lock = threading.Lock()
        self._t0 = time.perf_counter()
        self._cpu0 = time.process_time()
        self.latency_ms = 0.0

    # API de la traza
    def add_span(self, kind: str, name: str, started: float, ended: float, *, status: str = "ok", detail: dict | None = None, input_tokens: int | None = None, output_tokens: int | None = None) -> None:
        with self._lock:
            self.spans.append({"seq": len(self.spans) + 1, "kind": kind, "name": name, "start_ms": round((started - self._t0) * 1000, 1), "duration_ms": round((ended - started) * 1000, 1),
                               "status": status, "input_tokens": input_tokens, "output_tokens": output_tokens, "detail": detail or {}})

    @contextmanager
    def stage(self, name: str, **detail: Any):
        started = time.perf_counter()
        status = "ok"
        try:
            yield
        except Exception as error:
            status = "error"
            detail["error"] = type(error).__name__
            raise
        finally:
            self.add_span("stage", name, started, time.perf_counter(), status=status, detail=detail)

    def set(self, **fields: Any) -> None:
        for key in ("guardrails", "quality", "extra"):
            if key in fields:
                self.fields[key] = {**self.fields.get(key, {}), **(fields.pop(key) or {})}
        self.fields.update(fields)

    # Resumen
    def summary(self) -> dict[str, Any]:
        llm = [s for s in self.spans if s["kind"] == "llm"]
        tools = [s for s in self.spans if s["kind"] == "tool"]
        output = self.fields.get("output_text") or ""
        return {
            "run_id": self.run_id, "flow": self.flow, "user_hash": self.user_hash, "latency_ms": round(self.latency_ms, 1),
            "status": self.fields.get("status", "ok"), "model": self.model,
            "llm_calls": len(llm), "input_tokens": sum(s["input_tokens"] or 0 for s in llm), "output_tokens": sum(s["output_tokens"] or 0 for s in llm),
            "tool_calls": len(tools), "tool_errors": sum(1 for s in tools if s["status"] == "error"), "tools": [s["name"] for s in tools],
            "steps": int(self.fields.get("steps") or 0), "replans": int(self.fields.get("replans") or 0), "plan_source": self.fields.get("plan_source"),
            "input_chars": len(self.user_text), "output_chars": len(output), "guardrails": self.fields.get("guardrails", {}), "quality": self.fields.get("quality", {}),
            "error_type": self.fields.get("error_type"), "eval_tag": self.eval_tag,
            "extra": self.fields.get("extra", {}),  # causa del respaldo (llm_error), estado de la respuesta; sin texto del usuario
        }

    def __enter__(self) -> "RunTracer":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.latency_ms = (time.perf_counter() - self._t0) * 1000
        if exc is not None and self.fields.get("status") == "ok":
            self.fields["status"] = "error"
            self.fields["error_type"] = exc_type.__name__
            self.fields["error_message"] = redact(str(exc))[0][:300]
        self.finish()
        return False

    def finish(self) -> None:
        summary = self.summary()
        _ensure_file_log()
        log.info(json.dumps({"evento": "ejecucion_ia", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **summary}, ensure_ascii=False, default=str))
        if self.db is None or os.getenv("TRACE_PERSIST", "true").lower() in {"0", "false", "no", "off"}:
            return
        self._persist(summary)

    def _persist(self, summary: dict[str, Any]) -> None:
        from app.models.observability import AgentRun, AgentSpan

        try:
            with Session(bind=self.db.get_bind()) as session:
                session.add(AgentRun(
                    run_id=self.run_id, flow=self.flow, user_hash=self.user_hash, latency_ms=summary["latency_ms"], cpu_ms=round((time.process_time() - self._cpu0) * 1000, 1),
                    status=summary["status"], error_type=summary["error_type"], error_message=self.fields.get("error_message"), model=summary["model"],
                    llm_calls=summary["llm_calls"], input_tokens=summary["input_tokens"], output_tokens=summary["output_tokens"], tool_calls=summary["tool_calls"],
                    tool_errors=summary["tool_errors"], tools=summary["tools"], steps=summary["steps"], replans=summary["replans"], plan_source=summary["plan_source"],
                    input_chars=summary["input_chars"], output_chars=summary["output_chars"], input_preview=preview(self.user_text, 200),
                    guardrails=summary["guardrails"], quality=summary["quality"], eval_tag=self.eval_tag, extra=self.fields.get("extra", {}),
                ))
                session.flush()
                for span in self.spans:
                    session.add(AgentSpan(run_id=self.run_id, **span))
                session.commit()
        except Exception:  # noqa: BLE001 — la observabilidad nunca debe romper la respuesta
            log.warning("No se pudo guardar la traza %s", self.run_id, exc_info=True)
