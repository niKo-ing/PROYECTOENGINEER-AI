"""SOLOTODO AI V3 — Web Research + Evidence validation tests.

Deterministic and offline: every web interaction is mocked. No socket calls.
"""

from __future__ import annotations

from app.ai.evidence import Evidence, EvidenceKind, KnowledgeSourceType
from app.ai.research.benchmark import BenchmarkResult, extract_geekbench
from app.ai.research.chunking import ResearchDocument, chunk_text, document_to_chunks
from app.ai.research.reranker import rerank, score_result
from app.ai.research.schemas import ResearchQuery, ResearchReport, ResearchTarget, SearchResult
from app.ai.research.source_discovery import build_queries, is_official_source, target_identity
from app.ai.research.sources import confidence_for_source, source_priority, source_type_for_url, variant_matches
from app.ai.research.validation import (
    EvidenceVerdict,
    classify_evidence,
    extract_number_units,
    normalize_value,
    values_equivalent,
)
from app.ai.research.web_research_service import WebResearchService, _parse_ddg_results

POCO_X6 = ResearchTarget(id=1, name="POCO X6 5G", brand="Xiaomi", model="POCO X6", category="celulares")
IPHONE_15 = ResearchTarget(id=2, name="iPhone 15 Pro", brand="Apple", model="iPhone 15 Pro", category="celulares")


def evidence(*, title="", content="", source_type=KnowledgeSourceType.WEB, confidence=0.7) -> Evidence:
    return Evidence(
        source_type=source_type,
        source_name="Fuente de prueba",
        source_url="https://example.com/specs",
        title=title,
        content=content,
        confidence=confidence,
        kind=EvidenceKind.EXTRACTED,
    )


# ── Source priority (manufacturer-first) ────────────────────────────────

def test_source_priority_is_manufacturer_first():
    ranks = {
        KnowledgeSourceType.CATALOG: source_priority(KnowledgeSourceType.CATALOG),
        KnowledgeSourceType.MANUFACTURER: source_priority(KnowledgeSourceType.MANUFACTURER),
        KnowledgeSourceType.BENCHMARK: source_priority(KnowledgeSourceType.BENCHMARK),
        KnowledgeSourceType.REVIEW: source_priority(KnowledgeSourceType.REVIEW),
        KnowledgeSourceType.WEB: source_priority(KnowledgeSourceType.WEB),
    }
    assert ranks[KnowledgeSourceType.MANUFACTURER] > ranks[KnowledgeSourceType.BENCHMARK]
    assert ranks[KnowledgeSourceType.BENCHMARK] > ranks[KnowledgeSourceType.REVIEW]
    assert ranks[KnowledgeSourceType.REVIEW] > ranks[KnowledgeSourceType.WEB]
    assert source_priority(None) == 0
    assert confidence_for_source(KnowledgeSourceType.MANUFACTURER) >= confidence_for_source(KnowledgeSourceType.WEB)


def test_source_type_for_url_classification():
    assert source_type_for_url("https://www.asus.com/product/techspec/") == KnowledgeSourceType.MANUFACTURER
    assert source_type_for_url("https://browser.geekbench.com/...") == KnowledgeSourceType.BENCHMARK
    assert source_type_for_url("https://www.gsmarena.com/...") == KnowledgeSourceType.REVIEW
    assert source_type_for_url("https://algo-desconocido.com/x") == KnowledgeSourceType.WEB
    assert source_type_for_url(None) is None


# ── Variant matching (POCO X6 ≠ POCO X6 Pro) ────────────────────────────

def test_variant_matching_distinguishes_variants():
    assert variant_matches("POCO X6", ["POCO X6 Pro review"]) is False
    assert variant_matches("POCO X6 Pro", ["POCO X6 review"]) is False
    assert variant_matches("POCO X6", ["POCO X6 5G specs"]) is True
    assert variant_matches("POCO X6", ["Specs and benchmarks for the POCO X6"]) is True
    assert variant_matches("iPhone 15 Pro", ["Apple iPhone 15 128GB"]) is False
    assert variant_matches(None, ["cualquier cosa"]) is False


# ── Claim extraction and equivalence ────────────────────────────────────

def test_number_unit_extraction_normalization():
    assert extract_number_units("Geekbench Single 1234 points, 5 GHz, 12 GB RAM")[0] == (1234.0, "points")
    assert normalize_value("  8 GB  ") == "8 gb"
    assert values_equivalent("8 GB", "8 gigas") is True
    assert values_equivalent("8 GB", "8 GB") is True
    assert values_equivalent("8 GB", "16 GB") is False


def test_evidence_as_dict_keeps_provenance():
    item = evidence(title="RTX 4070 Super", content="boost 2.6 GHz", confidence=0.9)
    payload = item.as_dict()
    assert payload["source_type"] == "web"
    assert payload["source_url"] == "https://example.com/specs"
    assert payload["kind"] == "extracted"
    assert "retrieved_at" in payload


# ── Evidence validation ─────────────────────────────────────────────────

def test_classify_evidence_agreement_and_missing():
    verdict = classify_evidence([], claim="RAM", target_model="POCO X6")
    assert verdict.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE

    agreed = classify_evidence(
        [
            evidence(content="POCO X6 tiene 12 GB de RAM"),
            evidence(content="POCO X6 5G: 12 GB de RAM, 256 GB"),
        ],
        claim="RAM",
        target_model="POCO X6",
    )
    assert agreed.verdict == EvidenceVerdict.AGREEMENT
    assert agreed.confidence > 0.7


def test_classify_evidence_conflict():
    conflict = classify_evidence(
        [
            evidence(content="POCO X6 con 12 GB de RAM"),
            evidence(content="POCO X6 con 8 GB de RAM"),
        ],
        claim="RAM",
        target_model="POCO X6",
    )
    assert conflict.verdict == EvidenceVerdict.CONFLICT


def test_classify_evidence_variant_mismatch():
    mismatch = classify_evidence(
        [evidence(content="POCO X6 Pro 5G con 512 GB y 12GB")],
        claim="RAM",
        target_model="POCO X6",
    )
    assert mismatch.verdict == EvidenceVerdict.VARIANT_MISMATCH


def test_classify_evidence_irrelevant_skipped():
    verdict = classify_evidence(
        [evidence(content="NVIDIA RTX 4070 Super boost clock 2.6 GHz")],
        claim="RAM",
        target_model="POCO X6",
    )
    assert verdict.verdict == EvidenceVerdict.INSUFFICIENT_EVIDENCE


# ── Research planner (query building, manufacturer-first) ───────────────

def test_research_queries_are_manufacturer_first_and_budgeted():
    queries = build_queries([POCO_X6], "")
    assert queries
    assert queries[0].expected_type == KnowledgeSourceType.MANUFACTURER.value
    assert "specifications" in queries[0].query
    assert any(query.expected_type == KnowledgeSourceType.REVIEW.value for query in queries)
    assert all(query.target_id == POCO_X6.id for query in queries)

    capped = build_queries([POCO_X6, IPHONE_15], "¿hay benchmarks?", max_queries=2)
    assert len(capped) == 2
    assert all(isinstance(query, ResearchQuery) for query in capped)


def test_target_identity_falls_back_to_name_and_official_source():
    brand, model = target_identity(POCO_X6)
    assert brand == "Xiaomi"
    assert model == "POCO X6"

    nameless = ResearchTarget(id=3, name="Samsung Galaxy S24 Ultra", brand="Samsung")
    _brand, model2 = target_identity(nameless)
    assert model2 and "samsung" not in model2.casefold()  # fallback excludes brand from model

    assert is_official_source("https://www.samsung.com/phones/s24/", nameless) is True
    assert is_official_source("https://www.gsmarena.com/x.php", nameless) is False


# ── Reranker ────────────────────────────────────────────────────────────

def test_reranker_prefers_matching_variant_and_official_source():
    good = SearchResult(title="POCO X6 5G specs", url="https://www.mi.com/x6", snippet="12 GB RAM")
    pro = SearchResult(title="POCO X6 Pro review — distinto", url="https://example.com/pro", snippet="otra variante")
    unrelated = SearchResult(title="NVIDIA drivers", url="https://example.com/nv", snippet="drivers")
    ranked = rerank([pro, unrelated, good], POCO_X6, top_k=3)
    assert ranked[0].url == good.url
    assert score_result(good, POCO_X6) > score_result(pro, POCO_X6)
    assert score_result(unrelated, POCO_X6) == 0.0


# ── Chunking ────────────────────────────────────────────────────────────

def test_chunk_text_keeps_bounds_and_overlap():
    long = " ".join(["párrafo"] * 400)
    chunks = chunk_text(long, max_chars=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 200 + 5 for c in chunks)


def test_document_to_chunks_preserves_traceability():
    document = ResearchDocument(id="https://spec/1", title="POCO X6", content="c" * 2000, source_url="https://spec/1", source_name="spec")
    chunks = document_to_chunks(document, POCO_X6, max_chars=500, limit=24)
    assert chunks
    assert chunks[0].metadata["product_id"] == 1
    assert chunks[0].metadata["brand"] == "Xiaomi"
    assert chunks[0].metadata["model"] == "POCO X6"
    assert chunks[0].metadata["source_url"] == "https://spec/1"
    assert chunks[0].document_id == "https://spec/1"


# ── Benchmark extraction ────────────────────────────────────────────────

def test_extract_geekbench_preserves_version_and_type():
    scores = extract_geekbench("Geekbench 6 Single-Core 1521, Multi-Core 5412 (Measured 2026-08-01, stock)")
    single = next(item for item in scores if item.score_type == "single_core" and item.benchmark_version == "6")
    multi = next(item for item in scores if item.score_type == "multi_core")
    assert single.score == 1521
    assert multi.score == 5412
    assert single.score_type == "single_core"
    assert single.benchmark_name == "Geekbench 6"
    assert isinstance(single, BenchmarkResult)


# ── DuckDuckGo HTML parsing ─────────────────────────────────────────────

DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.mi.com%2Fpoco-x6&rut=abc">POCO X6 5G specs</a>
  <a class="result__snippet">8 Gen 2 · 12 GB RAM</a>
</div>
</body></html>
"""


def test_ddg_parser_extracts_title_url_snippet():
    results = _parse_ddg_results(DDG_HTML, max_results=5)
    assert len(results) == 1
    assert results[0].title == "POCO X6 5G specs"
    assert results[0].url == "https://www.mi.com/poco-x6"
    assert "12 GB RAM" in results[0].snippet


# ── WebResearchService (mocked search + retriever) ──────────────────────

class FakeSearch:
    def __init__(self, results: list[SearchResult]):
        self.results = results
        self.calls: list[str] = []

    def search(self, query: str, *, max_results=5, timeout_seconds=10.0):
        self.calls.append(query)
        return self.results


class FakeRetriever:
    def __init__(self, document: ResearchDocument | None = None):
        self.document = document
        self.calls: list[str] = []

    def retrieve(self, url: str, *, needles=(), timeout_seconds=10.0):
        self.calls.append((url, tuple(needles)))
        return self.document


class FailingSearch(FakeSearch):
    def search(self, query: str, *, max_results=5, timeout_seconds=10.0):
        self.calls.append(query)
        raise RuntimeError("network down")


def build_service(search, retriever=None, **kwargs):
    return WebResearchService(search, retriever or FakeRetriever(), **kwargs)


def test_service_runs_budgeted_research_and_builds_evidence():
    search = FakeSearch([SearchResult(title="POCO X6 5G specs", url="https://www.mi.com/poco-x6", snippet="12 GB RAM")])
    retriever = FakeRetriever(ResearchDocument(id="doc", title="POCO X6 5G", content="POCO X6 specifications. 12 GB RAM, 5G.", source_url="https://www.mi.com/poco-x6", source_name="mi.com"))
    service = build_service(search, retriever, max_queries=2, max_sources=3, max_documents=1, timeout_seconds=2)
    report = service.research([POCO_X6], "¿cuáles son sus benchmarks?")
    assert report.used is True
    assert report.queries_run <= 2
    assert report.evidence
    item = report.evidence[0]
    assert item.source_type == KnowledgeSourceType.MANUFACTURER  # mi.com is official
    assert item.source_url == "https://www.mi.com/poco-x6"
    assert report.sources[0]["source_type"] == item.source_type.value
    assert report.context and "Evidencia externa" in report.context
    assert search.calls  # network was consulted within budget


def test_service_returns_empty_report_when_max_queries_is_zero():
    service = build_service(FakeSearch([]), max_queries=0)
    report = service.research([POCO_X6], "")
    assert report.used is False
    assert report.evidence == []
    assert report.queries_run == 0


def test_service_survives_search_failures():
    service = build_service(FailingSearch([]), max_queries=2)
    report = service.research([POCO_X6], "")
    assert report.used is False
    assert report.evidence == []
    assert report.queries_run >= 1


def test_service_falls_back_to_snippet_when_retrieval_fails():
    search = FakeSearch([SearchResult(title="POCO X6 5G specs", url="https://spec/2", snippet="8 GB RAM, 256 GB")])
    retriever = FakeRetriever(None)
    service = build_service(search, retriever, max_queries=2, max_documents=1)
    report = service.research([POCO_X6], "")
    assert report.used is True
    assert report.evidence[0].content == "8 GB RAM, 256 GB"
    assert report.evidence[0].kind == EvidenceKind.EXTRACTED


def test_service_no_identity_yields_empty():
    target = ResearchTarget(id=9, name="Genérico", brand=None, model=None)
    service = build_service(FakeSearch([SearchResult(title="x", url="https://x", snippet="y")]), max_queries=2)
    report = service.research([target], "")
    assert report.used is False