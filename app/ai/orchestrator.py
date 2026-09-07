"""AI orchestration — deterministic intent → plan → evidence → answer.

The orchestrator reconstructs the conversation state from the client-provided
history, classifies the intent, resolves entities against the catalog, builds a
minimal execution plan, gathers structured evidence through the tool engine,
computes explainable comparisons/recommendations, and finally lets the LLM
provider write the natural-language answer over that evidence.

The provider contract is preserved: `request_tools` is always called (so tool
definitions stay visible to the model), LLM-requested calls run as before, and
`generate_final` receives the same tool outputs plus the deterministic evidence
in the prompt. Structured data (products, comparison, intent) is returned to the
frontend separately for cards and UI metadata.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.conversation_state import ConversationState
from app.ai.context_builder import AIContextBuilder, evidence_to_sections
from app.ai.engine.tool_engine import AIEngine
from app.ai.entity_resolution import EntityResolution, EntityResolver
from app.ai.intent import detect_intent
from app.ai.observability import new_trace_id, trace_step
from app.ai.planner import RESEARCH_CATALOG_ONLY, Planner
from app.ai.providers.base import LLMProvider, ProviderError, ProviderInvalidResponseError, ToolCall, Usage
from app.ai.recommendation import RecommendationEngine
from app.ai.research.query_planning import detect_topics
from app.ai.research.schemas import ResearchReport, ResearchTarget
from app.ai.research.source_discovery import target_identity
from app.ai.research.web_research_service import WebResearchService
from app.ai.schemas.chat import ChatResponse, ChatTurn, ChatUsage
from app.ai.schemas.intent import AIIntent, AIIntentType
from app.ai.schemas.tools import ToolExecutionRequest
from app.ai.tools.catalog import build_product_comparison
from app.core.config import settings
from app.core.security import AuthenticatedUser

_SOURCE_KINDS = {
    AIIntentType.COMPARE,
    AIIntentType.RECOMMEND,
    AIIntentType.PRODUCT_DETAIL,
    AIIntentType.SPECIFICATION,
    AIIntentType.PRICE_CHECK,
}

# Intents that may benefit from external research when the catalog lacks data.
# PRICE_CHECK is intentionally absent: prices only come from the catalog.
_RESEARCH_KINDS = {
    AIIntentType.COMPARE,
    AIIntentType.RECOMMEND,
    AIIntentType.PRODUCT_DETAIL,
    AIIntentType.SPECIFICATION,
}

_SEARCH_STOP = {
    "busca", "busco", "buscar", "busqu", "muestrame", "quiero", "necesito", "recomiendame",
    "recomienda", "un", "una", "unos", "unas", "el", "la", "los", "las", "de", "del", "para",
    "por", "hay", "con", "y", "o", "me", "te", "se", "en", "como", "que", "cual", "algo",
}


class AIOrchestrator:
    def __init__(self, db: Session, user: AuthenticatedUser, provider: LLMProvider, engine: AIEngine | None = None, research_service: WebResearchService | None = None):
        self.db = db
        self.user = user
        self.provider = provider
        self.tool_engine = engine or AIEngine(db, user)
        self.entity_resolver = EntityResolver(db)
        self.planner = Planner()
        self.recommendation_engine = RecommendationEngine()
        self.research_service = research_service
        self._knowledge_store = None
        self.trace: list[dict[str, Any]] = []
        self.trace_id = new_trace_id()

    def chat(
        self,
        message: str,
        product_id: int | None = None,
        history: list[ChatTurn] | None = None,
    ) -> ChatResponse:
        state = ConversationState.build(history or [], product_id)
        intent = detect_intent(message, state)
        resolution = self.entity_resolver.resolve_intent(message, intent, state)
        self._trace(
            "intent",
            {
                "intent": intent.intent.value,
                "requires_clarification": intent.requires_clarification,
                "constraints": list((intent.constraints or {}).keys()),
            },
        )

        if intent.requires_clarification or self._needs_clarification(intent, state, resolution):
            return ChatResponse(
                answer=self._clarification_answer(intent, resolution),
                tools_used=[],
                intent=intent.intent,
                need_clarification=True,
                products=[p.as_dict() for p in resolution.candidates],
            )

        prompt_message = message
        if intent.intent == AIIntentType.FOLLOW_UP:
            prompt_message = _expand_follow_up(message, state)
            self._trace("query_rewrite", {"original": message[:120], "rewritten": prompt_message[:240]})
        prompt = self._build_prompt(prompt_message, product_id, intent)
        try:
            initial = self.provider.request_tools(prompt, self.tool_engine.tool_definitions())
            outputs = self._execute_provider_calls(initial)
        except ProviderError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from error

        deterministic_outputs = self._execute_plan(state, intent, resolution, outputs)

        products = self._collect_products(state, resolution, outputs, deterministic_outputs)
        comparison = self._build_comparison(intent, products, message)

        report = self._run_research(prompt_message, intent, products, comparison)
        sources = report.sources if report else []
        research_context = report.context if report else None
        if report is not None and report.evidence and comparison is not None and comparison.get("winner_id") is not None:
            comparison["evidence"] = [item.as_dict() for item in report.evidence[:6]]
            comparison["unknowns"] = (comparison.get("unknowns") or []) + ([v.claim for v in report.verdicts if v.verdict and v.verdict.value == "insufficient_evidence"] if getattr(report, "verdicts", None) else [])

        if not initial.tool_calls:
            # The provider answered directly; keep its text (as before), but
            # still expose any deterministic products/comparison to the frontend.
            return self._response(initial, [], initial, products, comparison, intent, sources=sources, research=report is not None, evidence=[item.as_dict() for item in report.evidence] if report else None)

        evidence_prompt = self._augment_prompt(
            prompt,
            products,
            comparison,
            research_context=research_context,
            verdicts=report.verdicts if report else [],
            evidence=report.evidence if report else None,
        )

        try:
            final = self.provider.generate_final(evidence_prompt, initial, outputs)
        except ProviderError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from error

        used_tools = [output["name"] for output in outputs]
        return self._response(final, used_tools, initial, products, comparison, intent, sources=sources, research=report is not None, evidence=[item.as_dict() for item in report.evidence] if report else None)

    # ── Provider execution ──────────────────────────────────────────────

    def _execute_provider_calls(self, initial) -> list[dict]:
        outputs: list[dict] = []
        for call in initial.tool_calls[: settings.ai_max_tool_calls]:
            try:
                result = self.tool_engine.execute(ToolExecutionRequest(tool=call.name, parameters=call.arguments))
                outputs.append({"call_id": call.id, "name": call.name, "output": result.data})
            except HTTPException as error:
                outputs.append({"call_id": call.id, "name": call.name, "output": {"error": {"code": error.status_code, "detail": error.detail}}})
        return outputs

    # ── Deterministic plan execution (evidence only) ────────────────────

    def _execute_plan(self, state, intent, resolution, provider_outputs) -> list[dict]:
        plan = self.planner.build(intent, state, resolution, searchable_message=_searchable(intent, state))
        self._trace("planner", {"tools": plan.tools, "finished": plan.finished})
        outputs: list[dict] = []

        for index, step in enumerate(plan.steps):
            if _already_executed(provider_outputs, step):
                continue
            try:
                result = self.tool_engine.execute(ToolExecutionRequest(tool=step.tool, parameters=step.parameters))
                outputs.append({"call_id": f"plan-{index}", "name": step.tool, "output": result.data})
            except HTTPException:
                continue
        return outputs

    # ── Evidence assembly ───────────────────────────────────────────────

    def _collect_products(self, state, resolution, provider_outputs, plan_outputs) -> list[dict]:
        from_compare = _find_output(provider_outputs + plan_outputs, "compare_products")
        if from_compare:
            return _dedupe_products(p for p in from_compare["output"]["products"] if "error" not in p)

        from_search = _find_output(provider_outputs + plan_outputs, "search_products")
        if from_search:
            return _dedupe_products(list(from_search["output"].get("items") or []))

        if resolution.resolved:
            return [p.as_dict() for p in resolution.resolved]
        return [p.as_dict() for p in resolution.candidates]

    def _build_comparison(self, intent: AIIntent, products: list[dict], message: str) -> dict[str, Any] | None:
        if intent.intent == AIIntentType.RECOMMEND:
            objective = _wants_objective(message)
            recommendation = self.recommendation_engine.recommend(
                products,
                constraints=intent.constraints,
                objective=objective,
            )
            return recommendation.as_dict()
        if intent.intent == AIIntentType.COMPARE and products:
            return build_product_comparison(products)
        return None

    # ── External Web Research (catalog gaps only) ──────────────────────

    def _run_research(self, message: str, intent: AIIntent, products: list[dict], comparison: dict[str, Any] | None) -> ResearchReport | None:
        if not self._should_research(message, intent, products, comparison):
            return None
        targets = _to_research_targets(products)

        decision = self.planner.decide_research(
            intent,
            products_available=bool(products),
            has_spec_gaps=_has_spec_gaps(targets, comparison),
            wants_external=_wants_external_information(message),
            message=message,
        )
        if decision is not None and decision.mode != RESEARCH_CATALOG_ONLY:
            self._trace(
                "research_plan",
                {
                    "mode": decision.mode,
                    "depth": decision.depth.value,
                    "max_queries": decision.max_queries,
                    "max_sources": decision.max_sources,
                    "max_documents": decision.max_documents,
                    "reason": decision.reason,
                },
            )

        store = self._get_knowledge_store()
        if store is not None and (decision is None or decision.use_rag):
            kb_query = _kb_query(message, targets, topics=detect_topics(message))
            kb_report = store.search_research(kb_query, targets)
            if kb_report is not None and kb_report.used:
                self._trace("rag", {"hits": len(kb_report.evidence), "source": "knowledge_base"})
                return kb_report

        if decision is None or not decision.use_external:
            return None

        if self.research_service is None:
            self.research_service = WebResearchService.from_settings(db=self.db)
        if all(hasattr(self.research_service, attr) for attr in ("max_queries", "max_sources", "max_documents")):
            self.research_service.max_queries = min(self.research_service.max_queries, decision.max_queries)
            self.research_service.max_sources = min(self.research_service.max_sources, decision.max_sources)
            self.research_service.max_documents = min(self.research_service.max_documents, decision.max_documents)
        if hasattr(self.research_service, "research_depth"):
            self.research_service.research_depth = decision.depth
        report = self.research_service.research(targets, message)
        if report is not None and report.used:
            self._trace("web_research", {"evidence": len(report.evidence), "queries": report.queries_run, "depth": report.depth, "topics": report.topics or [], "source": "web"})
            if store is not None:
                try:
                    self.db.commit()
                except Exception:  # noqa: BLE001 — persistence is best-effort
                    self.db.rollback()
        return report if report is not None and report.used else None

    def _get_knowledge_store(self):
        """Lazy KB facade; enabled only through settings and never fatal when unavailable."""
        if self._knowledge_store is not None:
            return self._knowledge_store
        self._knowledge_store = False
        if not settings.rag_enabled:
            return None
        try:
            from app.ai.rag.knowledge_store import KnowledgeStore

            store = KnowledgeStore.from_settings(self.db)
        except Exception:  # noqa: BLE001 — RAG is an enhancement, never breaks chat
            return None
        self._knowledge_store = store
        return store

    def _trace(self, stage: str, data: dict[str, Any]) -> None:
        trace_step(self.trace, stage, data)

    def _should_research(self, message: str, intent: AIIntent, products: list[dict], comparison: dict[str, Any] | None) -> bool:
        if not settings.research_enabled or settings.max_research_queries <= 0:
            return False
        if intent.intent not in _RESEARCH_KINDS:
            return False
        if not products:
            return False
        targets = _to_research_targets(products)
        if not _has_target_identity(targets):
            return False
        decision = self.planner.decide_research(
            intent,
            products_available=True,
            has_spec_gaps=_has_spec_gaps(targets, comparison),
            wants_external=_wants_external_information(message),
            message=message,
        )
        return decision is not None and decision.use_external

    # ── Clarification ───────────────────────────────────────────────────

    def _needs_clarification(self, intent: AIIntent, state: ConversationState, resolution: EntityResolution) -> bool:
        if intent.intent not in _SOURCE_KINDS:
            return False
        if state.has_active_products() or state.product_anchor_id is not None:
            return False
        if resolution.resolved or resolution.candidates:
            return False
        if intent.intent == AIIntentType.RECOMMEND and intent.constraints.get("use_case"):
            return False
        return True

    @staticmethod
    def _clarification_answer(intent: AIIntent, resolution: EntityResolution) -> str:
        if resolution.candidates:
            names = ", ".join(candidate.name for candidate in resolution.candidates[:5])
            return f"Encontré varias opciones cercanas: {names}. ¿Sobre cuál o cuáles querés que te responda?"
        answers = {
            AIIntentType.COMPARE: "¿Qué productos querés comparar?",
            AIIntentType.RECOMMEND: "¿Qué productos querés considerar y cuál es tu presupuesto?",
            AIIntentType.PRODUCT_DETAIL: "¿Sobre qué producto necesitás el detalle?",
            AIIntentType.SPECIFICATION: "¿Qué producto o qué especificación querés consultar?",
            AIIntentType.PRICE_CHECK: "¿De qué producto querés conocer el precio?",
        }
        return answers.get(intent.intent, "¿Podés darme un poco más de detalle?")

    # ── Prompt building ─────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(message: str, product_id: int | None, intent: AIIntent) -> str:
        analysis = f"[Análisis del sistema: intención={intent.intent.value}; restricciones={intent.constraints or None}]"
        prompt = f"{message}\n\n{analysis}"
        if product_id is not None:
            prompt += (
                f"\n\n[Contexto del sistema: el usuario consulta desde la página del producto con id {product_id}. "
                f"Si su pregunta se refiere a 'este producto' o al producto, usá ese id con los tools del catálogo. "
                f"No inventes datos.]"
            )
        return prompt

    @staticmethod
    def _augment_prompt(
        prompt: str,
        products: list[dict],
        comparison: dict[str, Any] | None,
        research_context: str | None = None,
        verdicts: list | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> str:
        lines = []
        if products:
            summary = " | ".join(
                _product_label(product) for product in products[:8]
            )
            lines.append(f"Productos relevantes del catálogo: {summary}")
        if comparison and comparison.get("winner_id") is not None:
            lines.append("Recomendación del sistema basada en specs/precios: " + (comparison.get("winner_reason") or "opción equilibrada."))
            criteria = comparison.get("criteria") or {}
            if criteria:
                lines.append("Criterios considerados: " + ", ".join(f"{key}={value}" for key, value in criteria.items()))
            tradeoffs = comparison.get("tradeoffs") or {}
            line = "; ".join(
                f"{_product_name(products, int(key)) or ('producto ' + key)} pierde en {', '.join(values[:4]) or 'ninguno'}"
                for key, values in list(tradeoffs.items())[:5]
            )
            if line:
                lines.append(line)
        if verdicts or evidence:
            rendered = evidence_to_sections(verdicts, evidence=[item for item in (evidence or [])])
            grounded = AIContextBuilder(token_limit=settings.rag_token_budget).build("", rendered) if rendered else ""
            sections = [("catalog", "\n".join(lines)), ("research", grounded)]
        else:
            sections = [("catalog", "\n".join(lines)), ("research", research_context)]
        block = AIContextBuilder(token_limit=settings.rag_token_budget).build("", sections)
        if not block.strip():
            return prompt
        return prompt + "\n\n" + block.strip()

    # ── Response helpers ────────────────────────────────────────────────

    def _response(self, final, used_tools: list[str], initial, products: list[dict], comparison: dict[str, Any] | None, intent: AIIntent, sources: list[dict] | None = None, research: bool = False, evidence: list[dict[str, Any]] | None = None) -> ChatResponse:
        if not final.text.strip():
            raise HTTPException(status_code=502, detail=ProviderInvalidResponseError.detail)
        usage = _combine_usage(initial.usage, final.usage)
        response_usage = ChatUsage(model=usage.model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, latency_ms=usage.latency_ms) if usage else None
        is_recommendation = bool(comparison and comparison.get("winner_id") is not None)
        return ChatResponse(
            answer=final.text,
            tools_used=used_tools,
            usage=response_usage,
            products=products,
            comparison=comparison,
            intent=intent.intent,
            need_clarification=False,
            sources=sources or [],
            research=research,
            recommendation=comparison if is_recommendation else None,
            evidence=[dict(item) for item in (evidence or [])][:12],
            trace=list(self.trace),
            trace_id=self.trace_id,
        )


# ── Module helpers ──────────────────────────────────────────────────────

def _searchable(intent: AIIntent, state: ConversationState) -> str | None:
    for entity in intent.entities:
        if entity.family:
            return entity.family[:120]
        if entity.model:
            return entity.model[:120]
        if entity.brand:
            return entity.brand[:120]
    if state.current_topic and len(state.current_topic) > 3:
        tokens = [
            token
            for token in state.current_topic.casefold().split()
            if token not in _SEARCH_STOP and any(ch.isalnum() for ch in token)
        ]
        if tokens:
            return " ".join(tokens[-6:])[:120]
    return None


def _wants_objective(text: str) -> bool:
    return bool(re.search(r"cual es mejor|mejor opcion|mejor entre|mejor compra|best|el mejor", text.casefold()))


def _product_label(product: dict) -> str:
    name = product.get("name") or "producto"
    price = product.get("lowest_price") or product.get("price_clp") or "s/p"
    return f"{name} (${price})"


def _product_name(products: list[dict], product_id: int) -> str | None:
    for product in products:
        if product.get("id") == product_id:
            return product.get("name")
    return None


def _dedupe_products(products) -> list[dict]:
    seen: dict[int, dict] = {}
    for product in products:
        pid = product.get("id")
        if pid is None:
            continue
        seen.setdefault(pid, product)
    return list(seen.values())


def _already_executed(provider_outputs: list[dict], step) -> bool:
    if step.tool != "compare_products" and step.tool != "search_products":
        return False
    params = step.parameters or {}
    if step.tool == "compare_products":
        wanted = set(params.get("product_ids") or [])
        for output in provider_outputs:
            if output["name"] == "compare_products" and wanted.issubset(set((output["output"].get("products") and [p.get("id") for p in output["output"]["products"] if "error" not in p]) or [])):
                return True
    elif step.tool == "search_products":
        for output in provider_outputs:
            if output["name"] == "search_products":
                return True
    return False


def _find_output(outputs: list[dict], tool: str) -> dict | None:
    return next((output for output in outputs if output["name"] == tool and "error" not in output.get("output", {})), None)


def _combine_usage(first: Usage | None, second: Usage | None) -> Usage | None:
    if first is None:
        return second
    if second is None:
        return first
    return Usage(
        model=second.model,
        input_tokens=(first.input_tokens or 0) + (second.input_tokens or 0),
        output_tokens=(first.output_tokens or 0) + (second.output_tokens or 0),
        latency_ms=(first.latency_ms or 0) + (second.latency_ms or 0),
    )


# ── External research helpers ───────────────────────────────────────────

_RESEARCH_WORDS = (
    "benchmark", "geekbench", "score", "puntaje", "rendimiento", "performance",
    "review", "opiniones", "reseñas", "resenas", "analisis", "análisis",
    "fabricante", "oficial", "especificaciones oficiales", "fuera del catalogo",
    "fuera del catálogo", "comentarios", "comparativa externa", "mejor puntaje",
    "web", "internet", "notas del fabricante",
)


def _wants_external_information(message: str) -> bool:
    lowercase = message.casefold()
    return any(word in lowercase for word in _RESEARCH_WORDS)


def _expand_follow_up(message: str, state: ConversationState) -> str:
    """Reconstruct a bare follow-up ("¿y cuál es mejor?") with its prior context."""
    for turn in reversed(state.turns):
        if turn.role == "user":
            base = (turn.content or "").strip()
            if base and base != message:
                return f"{base} {message}".strip()
    return message


def _to_research_targets(products: list[dict]) -> list[ResearchTarget]:
    return [
        ResearchTarget(
            id=product.get("id") or 0,
            name=product.get("name") or "",
            brand=product.get("brand"),
            model=product.get("model"),
            category=product.get("category"),
            specs=dict(product.get("specs") or {}),
        )
        for product in products[:5]
    ]


def _kb_query(message: str, targets: list[ResearchTarget], topics: list[str] | None = None) -> str:
    """Augment the user query with the resolved product identity and detected
    topics so keyword and local-hash retrieval can match stored documents."""
    identity = " ".join(
        f"{brand or ''} {model or ''}".strip()
        for brand, model in (target_identity(target) for target in targets)
        if brand or model
    )
    topic_terms = " ".join(
        {
            "benchmarks": "benchmark",
            "reviews": "review",
            "especificaciones": "specifications",
            "precio": "price",
            "gaming": "gaming",
            "productividad": "productivity",
            "consumo": "power",
            "compatibilidad": "compatibility",
        }.get(topic, topic)
        for topic in (topics or [])
    )
    context = " ".join(part for part in (identity, topic_terms) if part)
    return f"{message} {context}".strip() if context else message


def _has_target_identity(targets: list[ResearchTarget]) -> bool:
    return any(brand or model for brand, model in (target_identity(target) for target in targets))


def _has_spec_gaps(targets: list[ResearchTarget], comparison: dict[str, Any] | None) -> bool:
    if comparison and isinstance(comparison, dict):
        dimensions = comparison.get("dimensions") or {}
        if dimensions and any(dim.get("missing") for dim in dimensions.values()):
            return True
    for target in targets:
        brand, model = target_identity(target)
        if (brand or model) and not (target.specs or {}):
            return True
    return False