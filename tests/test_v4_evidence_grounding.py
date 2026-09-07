"""AI V4 — grounded answering: conflict resolution and the grounded prompt.

Verifies that contradictory sources are resolved deterministically by
priority/confidence/freshness (or honestly left as "no sé"), that the grounded
prompt labels verdicts so the LLM cannot hallucinate unsupported specs, and
that variant mismatch never claims a spec belongs to another SKU.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.ai.context_builder import build_grounded_prompt, evidence_to_sections
from app.ai.evidence import Claim, ClaimType, Evidence, EvidenceKind, KnowledgeSourceType
from app.ai.research.validation import EvidenceVerdict, resolve_claim


def _evidence(text: str, source_type, confidence=1.0, retrieved_days_ago=0, *, source_name="Fuente") -> Evidence:
    return Evidence(
        source_type=source_type,
        source_name=source_name,
        content=text,
        confidence=confidence,
        kind=EvidenceKind.EXTRACTED,
        retrieved_at=datetime.now(timezone.utc) - timedelta(days=retrieved_days_ago),
        claim_type=ClaimType.PERFORMANCE,
    )


def test_insufficient_evidence_is_reported_not_invented():
    verdict = resolve_claim([], claim="consume 270W")
    assert verdict.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE
    assert "Sin evidencia" in (verdict.note or "")


def test_agreement_on_consistent_numbers():
    items = [
        _evidence("La RTX 5070 Ti consume 270W bajo carga.", KnowledgeSourceType.BENCHMARK, confidence=0.9),
        _evidence("El consumo maximo de la RTX 5070 Ti es 270W.", KnowledgeSourceType.REVIEW, confidence=0.8),
    ]
    verdict = resolve_claim(items, claim="consumo", target_model="RTX 5070 Ti")
    assert verdict.verdict == EvidenceVerdict.AGREEMENT
    assert verdict.confidence >= 0.9
    assert len(verdict.supported_by) == 2


def test_conflict_is_resolved_by_source_weight():
    # Manufacturer (priority 50) vs web (priority 20) disagree on the number;
    # resolve_claim must pick the dominant source deterministically.
    discount = _evidence("El consumo oficial de la RTX 5070 Ti es 270W.", KnowledgeSourceType.MANUFACTURER, confidence=0.95, source_name="NVIDIA")
    correct = _evidence("El consumo de la RTX 5070 Ti es 210W.", KnowledgeSourceType.WEB, confidence=0.6, source_name="random-blog")
    items = [correct, discount]
    verdict = resolve_claim(items, claim="consumo", target_model="RTX 5070 Ti")
    assert verdict.verdict == EvidenceVerdict.AGREEMENT, verdict.note
    assert "resuelto" in (verdict.note or "").casefold()
    winner = verdict.supported_by[0]
    assert winner.source_name == "NVIDIA"


def test_unresolvable_conflict_stays_conflict_and_honest():
    # Two review sources with equal weight → keep CONFLICT and say so.
    items = [
        _evidence("la rtx 5070 ti consume 210w segun mediciones", KnowledgeSourceType.REVIEW, confidence=0.8, source_name="Review A"),
        _evidence("la rtx 5070 ti consume 270w en carga plena", KnowledgeSourceType.REVIEW, confidence=0.8, source_name="Review B"),
    ]
    verdict = resolve_claim(items, claim="consumo", target_model="RTX 5070 Ti")
    assert verdict.verdict == EvidenceVerdict.CONFLICT
    assert "no resuelto" in (verdict.note or "").casefold()


def test_variant_mismatch_does_not_claim_other_sku():
    items = [
        _evidence("La RTX 5070 Laptop 115W consume 80W.", KnowledgeSourceType.REVIEW),
    ]
    verdict = resolve_claim(items, claim="consumo", target_model="RTX 5070 Ti")
    assert verdict.verdict == EvidenceVerdict.VARIANT_MISMATCH
    assert "variante" in (verdict.note or "").casefold()


def test_evidence_to_sections_labels_verdicts_for_the_llm():
    agreement = _evidence("La RTX 5070 Ti rinde fuerte a 1440p.", KnowledgeSourceType.BENCHMARK, source_name="TechSpot")
    conflict_low = _evidence("la rtx 5070 ti consume 210w", KnowledgeSourceType.REVIEW, source_name="Review A")
    conflict_high = _evidence("la rtx 5070 ti consume 270w", KnowledgeSourceType.REVIEW, source_name="Review B")
    verdicts = [
        resolve_claim([agreement], claim="rendimiento 1440p"),
        resolve_claim([conflict_low, conflict_high], claim="consumo"),
    ]
    sections = evidence_to_sections(verdicts, [agreement, conflict_low, conflict_high])
    labels = " ".join(body for _section, body in sections).casefold()
    assert "rendimiento 1440p" in labels
    assert "apoya" in labels
    assert "conflicto" in labels

    for section, body in sections:
        assert body, "each grounded section must render its verdict body"

    prompt = build_grounded_prompt(prompt="Pregunta", verdicts=verdicts, evidence=[agreement, conflict_low, conflict_high], token_limit=4000)
    assert "TechSpot" in prompt
    assert "CONFLICTO" in prompt or "conflicto" in prompt.casefold()


def test_grounded_prompt_never_offers_unbacked_specs():
    verdict = resolve_claim([], claim="soporta wifi 7")
    prompt = build_grounded_prompt(
        prompt="¿Qué RAM soporta?",
        verdicts=[verdict],
        evidence=[],
        token_limit=2000,
    )
    assert "sin confirmar" in prompt.casefold()
    # The model is told to answer only what the grounded sections support.
    assert "unicamente" in prompt.casefold()
    assert "no sab" in prompt.casefold()