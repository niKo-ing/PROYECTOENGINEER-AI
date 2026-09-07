"""AIContextBuilder — bounded, sectioned context assembly for the LLM.

Replaces ad-hoc prompt concatenation: receives an ordered list of optional
sections, drops empty ones, and truncates oversized sections to a configurable
token budget so the context shown to the model stays small and relevant instead
of "sending everything indiscriminately".
"""

from __future__ import annotations

from typing import Any

CHARS_PER_TOKEN = 3.5

DEFAULT_SECTION_HEADER = "[Evidencia determinística — usala al redactar la respuesta, sin inventar datos]"


def _approx_chars(text: str) -> int:
    return len(text)


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rfind(" ")
    return text[: cut if cut > 0 else max_chars - 1].rstrip() + "…"


class AIContextBuilder:
    def __init__(self, *, token_limit: int = 1600, reserved_for_answer: int = 500):
        self.token_limit = max(int(token_limit), 200)
        self.reserved_for_answer = max(int(reserved_for_answer), 0)

    def budget_chars(self) -> int:
        return int(max((self.token_limit - self.reserved_for_answer), 0) * CHARS_PER_TOKEN)

    def build(
        self,
        prompt: str,
        sections: list[tuple[str, str | None]],
        *,
        header: str = DEFAULT_SECTION_HEADER,
    ) -> str:
        """Append non-empty sections to ``prompt`` respecting the token budget."""
        remaining = self.budget_chars()
        parts: list[str] = []
        for _label, body in sections:
            body = (body or "").strip()
            if not body:
                continue
            if len(body) > remaining:
                body = _truncate(body, remaining)
                if not body:
                    continue
            remaining -= _approx_chars(body)
            parts.append(body)
        if not parts:
            return prompt
        return prompt + "\n\n" + header + "\n" + "\n".join(parts)


def build_sectioned_prompt(*, prompt: str, sections: list[tuple[str, str | None]], token_limit: int = 1600, header: str = DEFAULT_SECTION_HEADER) -> str:
    return AIContextBuilder(token_limit=token_limit).build(prompt, sections, header=header)


_GROUNDED_HEADER = "[Evidencia — respondé UNICAMENTE con datos respaldados; si hay conflicto o no hay evidencia, decí que no sabés]"


def evidence_to_sections(verdicts: list, evidence: list | None = None) -> list[tuple[str, str | None]]:
    """Render claim verdicts + evidence into bounded prompt sections (grounding policy).

    Each claim becomes a labelled section with its verdict (apoya / conflicto /
    no aplica / no confirmado), the supporting sources and any conflicting ones,
    so the model can decide what it is allowed to assert. Returns ``[]`` when
    there is nothing renderable.
    """
    labels = {
        "agreement": "apoya",
        "conflict": "CONFLICTO",
        "variant_mismatch": "no aplica a la variante",
        "insufficient_evidence": "sin confirmar",
    }
    sections: list[tuple[str, str | None]] = []
    for verdict in verdicts or []:
        label = labels.get(getattr(getattr(verdict, "verdict", None), "value", ""), "sin evidencia")
        lines = [f"- {verdict.claim}: {label}"]
        for item in verdict.supported_by:
            lines.append(f"  · apoya [{item.source_name}]({item.source_url})" if item.source_url else f"  · apoya {item.source_name}")
        for item in verdict.conflicts_with:
            lines.append(f"  · en contra [{item.source_name}]({item.source_url})" if item.source_url else f"  · en contra {item.source_name}")
        body = "\n".join(lines)
        if body.strip():
            sections.append((verdict.claim, body))

    if evidence:
        listed = "\n".join(f"- {item.source_name}: {item.title or item.source_url}" for item in evidence)
        if listed.strip():
            sections.append(("fuentes", listed))
    return sections


def build_grounded_prompt(*, prompt: str, verdicts: list, evidence: list | None = None, token_limit: int = 1600) -> str:
    """Assemble a prompt whose context only contains grounded, verdict-tagged claims."""
    sections = evidence_to_sections(verdicts, evidence=evidence)
    return AIContextBuilder(token_limit=token_limit).build(prompt, sections, header=_GROUNDED_HEADER)