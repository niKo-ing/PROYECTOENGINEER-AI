"""Gemini-based AI matching provider.

Uses structured output (JSON schema) to ensure deterministic parsing.
Validates response before returning.

Security: only sends product attributes necessary for matching.
No credentials, no tokens, no internal DB IDs in prompts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.catalog.ai_matching import (
    AIMatchRequest,
    AIMatchResult,
    AIMatchStatus,
    AIMatchingProvider,
)
from app.catalog.ai_config import AIMatchingConfig

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un asistente de matching de productos de tecnología para un comparador de precios chileno.

Tu tarea: determinar si un producto nuevo es el MISMO producto que uno de los candidatos existentes.

REGLAS ESTRICTAS:
1. Prioriza: GTIN > MPN > manufacturer SKU > brand+model > especificaciones > título
2. Un título similar NO significa necesariamente mismo producto
3. Diferencias en RAM, almacenamiento, VRAM, tamaño de pantalla, color, generación = PRODUCTOS DIFERENTES
4. Si hay duda razonable, responde AMBIGUOUS
5. NUNCA asumas sin evidencia

IMPORTANTE: El campo "sku" del producto entrante es el retailer_item_id de la tienda, NO es un manufacturer_sku. No lo uses para matching.

Responde ÚNICAMENTE con JSON válido que siga el esquema proporcionado."""


def _build_user_prompt(request: AIMatchRequest) -> str:
    """Build the user prompt with structured product information."""
    lines = ["## Producto nuevo a evaluar\n"]
    lines.append(f"- Título: {request.incoming_name}")
    if request.incoming_brand:
        lines.append(f"- Marca: {request.incoming_brand}")
    if request.incoming_model:
        lines.append(f"- Modelo: {request.incoming_model}")
    if request.incoming_mpn:
        lines.append(f"- MPN: {request.incoming_mpn}")
    if request.incoming_gtin:
        lines.append(f"- GTIN: {request.incoming_gtin}")
    if request.incoming_manufacturer_sku:
        lines.append(f"- Manufacturer SKU: {request.incoming_manufacturer_sku}")
    if request.incoming_specifications:
        lines.append("- Especificaciones:")
        for k, v in request.incoming_specifications.items():
            lines.append(f"  - {k}: {v}")

    lines.append(f"\n## {len(request.candidates)} Candidatos existentes\n")

    for i, c in enumerate(request.candidates, 1):
        lines.append(f"### Candidato {i} (ID: {c.product_id})\n")
        lines.append(f"- Título: {c.name}")
        if c.brand:
            lines.append(f"- Marca: {c.brand}")
        if c.model:
            lines.append(f"- Modelo: {c.model}")
        if c.mpn:
            lines.append(f"- MPN: {c.mpn}")
        if c.gtin:
            lines.append(f"- GTIN: {c.gtin}")
        if c.manufacturer_sku:
            lines.append(f"- Manufacturer SKU: {c.manufacturer_sku}")
        if c.specifications:
            lines.append("- Especificaciones:")
            for k, v in c.specifications.items():
                lines.append(f"  - {k}: {v}")
        lines.append("")

    lines.append("## Instrucciones\n")
    lines.append("Evalúa si el producto nuevo coincide con alguno de los candidatos.")
    lines.append("Responde con JSON: {\"decision\": \"match\"|\"no_match\"|\"ambiguous\", \"confidence\": 0.0-1.0, \"matched_product_id\": <id|null>, \"reason\": \"explicación breve\", \"evidence\": {\"campo\": \"valor\"}}")

    return "\n".join(lines)


def _response_schema() -> dict[str, Any]:
    """JSON schema for structured output validation."""
    return {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["match", "no_match", "ambiguous"],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "matched_product_id": {
                "type": ["integer", "null"],
            },
            "reason": {
                "type": "string",
            },
            "evidence": {
                "type": "object",
            },
        },
        "required": ["decision", "confidence", "reason"],
    }


class GeminiMatchingProvider(AIMatchingProvider):
    """Gemini-based AI matching with structured output.

    Uses the Google GenAI SDK with JSON response schema.
    Validates response schema and candidate IDs before returning.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        config: AIMatchingConfig | None = None,
        client: Any | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.config = config or AIMatchingConfig()
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from google import genai
        from google.genai import types

        self._client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=int(self.config.timeout_seconds * 1000)
            ),
        )
        return self._client

    def match(self, request: AIMatchRequest) -> AIMatchResult:
        """Call Gemini with structured output and validate response."""
        from google.genai import types

        client = self._get_client()
        user_prompt = _build_user_prompt(request)
        schema = _response_schema()

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.0,
        )

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=config,
            )
        except TimeoutError as e:
            log.warning("AI matching timeout: %s", e)
            return AIMatchResult(
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.0,
                reason="AI timeout",
                model=self.model,
                prompt_version=request.prompt_version,
            )
        except Exception as e:
            log.warning("AI matching error: %s: %s", type(e).__name__, e)
            return AIMatchResult(
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.0,
                reason=f"AI error: {type(e).__name__}",
                model=self.model,
                prompt_version=request.prompt_version,
            )

        return self._parse_response(response, request)

    def _parse_response(self, response: Any, request: AIMatchRequest) -> AIMatchResult:
        """Parse and validate Gemini response."""
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return self._error_result("No candidates in response", request)

        candidate = candidates[0]
        content = getattr(candidate, "content", None)
        if content is None:
            return self._error_result("No content in response", request)

        text = ""
        for part in getattr(content, "parts", []):
            part_text = getattr(part, "text", None)
            if part_text:
                text = part_text
                break

        if not text:
            return self._error_result("Empty response text", request)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return self._error_result(f"Invalid JSON: {e}", request)

        return self._validate_and_build(data, request)

    def _validate_and_build(
        self, data: dict[str, Any], request: AIMatchRequest
    ) -> AIMatchResult:
        """Validate response data and build AIMatchResult."""
        decision_str = data.get("decision", "ambiguous")
        try:
            decision = AIMatchStatus(decision_str)
        except ValueError:
            return self._error_result(f"Invalid decision: {decision_str}", request)

        confidence = data.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            confidence = 0.0
        confidence = max(0.0, min(1.0, float(confidence)))

        matched_id = data.get("matched_product_id")
        if matched_id is not None:
            if not isinstance(matched_id, int):
                return self._error_result("matched_product_id must be int or null", request)
            candidate_ids = {c.product_id for c in request.candidates}
            if matched_id not in candidate_ids:
                return self._error_result(
                    f"matched_product_id {matched_id} not in candidates {candidate_ids}",
                    request,
                )

        reason = data.get("reason", "")
        evidence = data.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}

        return AIMatchResult(
            decision=decision,
            confidence=confidence,
            matched_product_id=matched_id,
            reason=reason,
            evidence=evidence,
            model=self.model,
            prompt_version=request.prompt_version,
        )

    def _error_result(self, reason: str, request: AIMatchRequest) -> AIMatchResult:
        log.warning("AI matching validation failed: %s", reason)
        return AIMatchResult(
            decision=AIMatchStatus.AMBIGUOUS,
            confidence=0.0,
            reason=reason,
            model=self.model,
            prompt_version=request.prompt_version,
        )
