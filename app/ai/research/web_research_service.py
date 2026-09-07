"""Web Research service — provider + document retrieval + validation.

The service is fully injectable (protocols, not hard bindings): the default
provider is DuckDuckGo HTML search (no API key, deterministic parsing) and the
default retriever is a rebounded httpx fetch that reuses the catalog
``spec_fetch`` normalization. Everything is budget-limited and every artifact
falls back to ``KnowledgeSourceType.WEB`` provenance.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Protocol

import httpx
from bs4 import BeautifulSoup

from app.ai.evidence import Evidence, EvidenceKind, KnowledgeSourceType
from app.ai.research.benchmark import extract_geekbench
from app.ai.research.chunking import ResearchDocument, document_to_chunks
from app.ai.research.reranker import rerank, source_for_result
from app.ai.research.schemas import ResearchQuery, ResearchReport, ResearchTarget, SearchResult
from app.ai.research.source_discovery import build_queries, target_identity
from app.ai.research.sources import confidence_for_source
from app.ai.research.validation import ClaimVerdict, classify_evidence

_DDG_URL = "https://html.duckduckgo.com/html/"
_DDG_PARAMS = ("kl=us-en", "ia=web")
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en;q=0.8,es;q=0.7,*;q=0.5",
}


class WebSearchProvider(Protocol):
    """Search the web for query links. Implementations must never raise."""

    def search(self, query: str, *, max_results: int = 5, timeout_seconds: float = 10.0) -> list[SearchResult]: ...


class DocumentRetriever(Protocol):
    """Fetch a single document as normalized text (main content, bounded)."""

    def retrieve(self, url: str, *, needles: tuple[str, ...] = (), timeout_seconds: float = 10.0) -> ResearchDocument | None: ...


class DuckDuckGoSearchProvider:
    """HTML search provider against DuckDuckGo's no-JS endpoint.

    Pure ``httpx`` + ``BeautifulSoup``; no API key required. An injected
    ``client`` keeps tests hermetic without touching the network.
    """

    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def search(self, query: str, *, max_results: int = 5, timeout_seconds: float = 10.0) -> list[SearchResult]:
        payload = "&".join((*_DDG_PARAMS, f"q={urllib.parse.quote_plus(query)}"))
        try:
            make_request = (self._client or httpx).get
            response = make_request(f"{_DDG_URL}?{payload}", headers=_DDG_HEADERS, timeout=timeout_seconds, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        return _parse_ddg_results(response.text, max_results=max_results)


_DDG_HEADERS = {**_DEFAULT_HEADERS, "Accept": "text/html,application/xhtml+xml"}


def _parse_ddg_results(html: str, *, max_results: int = 5) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []
    for anchor in soup.select("a.result__a")[:max_results]:
        title = anchor.get_text(" ", strip=True)
        href = anchor.get("href") or ""
        url = _uddg_target(href) or href
        if not title or not url:
            continue
        result = anchor.find_parent("div", class_="result")
        snippet = ""
        if result is not None:
            snippet_node = result.select_one(".result__snippet")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        results.append(SearchResult(title=title, url=url, snippet=snippet))
    return results


def _uddg_target(href: str) -> str | None:
    if "uddg=" not in href:
        return None
    parsed = urllib.parse.urlparse(href)
    params = urllib.parse.parse_qs(parsed.query)
    target = params.get("uddg")
    return target[0] if target else None


class HTTPDocumentRetriever:
    """Fetch a URL and reduce it to main plain-text content using catalog norms."""

    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def retrieve(self, url: str, *, needles: tuple[str, ...] = (), timeout_seconds: float = 10.0) -> ResearchDocument | None:
        try:
            make_request = (self._client or httpx).get
            response = make_request(url, headers=_DEFAULT_HEADERS, timeout=timeout_seconds, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        if not response.text:
            return None
        title = _document_title(response.text)
        from app.catalog.spec_fetch import normalize_context

        content = normalize_context(response.text, needles or ()) or ""
        if not content:
            return None
        return ResearchDocument(
            id=url,
            title=title,
            content=content,
            source_url=str(response.url),
            source_name=_display_host(url),
        )


def _document_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title")
    return title.get_text(" ", strip=True) if title else None


def _display_host(url: str) -> str:
    stripped = url.split("://", 1)[-1]
    return stripped.split("/", 1)[0].split(":", 1)[0].casefold()


class WebResearchService:
    """Deterministic, budget-limited research over catalog gaps.

    Callers must only invoke it when the catalog is actually missing information
    (see orchestrator gating). ``max_queries <= 0`` disables all external calls.
    """

    def __init__(
        self,
        search: WebSearchProvider,
        retriever: DocumentRetriever,
        *,
        max_queries: int = 3,
        max_sources: int = 4,
        max_documents: int = 3,
        max_chunks: int = 24,
        max_chars: int = 6000,
        timeout_seconds: float = 10.0,
    ):
        self.search = search
        self.retriever = retriever
        self.max_queries = max_queries
        self.max_sources = max_sources
        self.max_documents = max_documents
        self.max_chunks = max_chunks
        self.max_chars = max_chars
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, __settings=None) -> "WebResearchService":
        from app.core.config import settings as default_settings

        settings = __settings or default_settings
        return cls(
            DuckDuckGoSearchProvider(),
            HTTPDocumentRetriever(),
            max_queries=settings.max_research_queries,
            max_sources=settings.max_research_sources,
            max_documents=settings.max_research_documents,
            max_chunks=settings.max_research_chunks,
            max_chars=settings.max_research_chars,
            timeout_seconds=settings.research_timeout_seconds,
        )

    def research(self, targets: list[ResearchTarget], message: str = "") -> ResearchReport:
        if self.max_queries <= 0 or not targets:
            return ResearchReport(used=False, evidence=[], queries_run=0, note="Research deshabilitado.")

        queries = build_queries(targets, message, max_queries=self.max_queries)
        if not queries:
            return ResearchReport(used=False, evidence=[], queries_run=0, note="Sin identidad de producto para investigar.")

        results_by_target: dict[int, list[SearchResult]] = {}
        queries_run = 0
        for query in queries:
            if queries_run >= self.max_queries:
                break
            hits = self._search(query)
            queries_run += 1
            if query.target_id is not None:
                results_by_target.setdefault(query.target_id, []).extend(hits)

        selected = self._select(results_by_target, targets)
        evidence = self._collect_evidence(selected)

        verdicts = self._verdicts(evidence, targets)
        context = self._build_context(evidence, verdicts)
        note = self._note(queries_run, evidence)
        return ResearchReport(
            used=bool(evidence),
            evidence=evidence,
            verdicts=verdicts,
            queries_run=queries_run,
            context=context,
            note=note,
        )

    # ── Steps ──────────────────────────────────────────────────────────

    def _search(self, query: ResearchQuery) -> list[SearchResult]:
        try:
            return self.search.search(query.query, max_results=5, timeout_seconds=self.timeout_seconds)
        except Exception:
            return []

    def _select(self, results_by_target: dict[int, list[SearchResult]], targets: list[ResearchTarget]) -> list[tuple[SearchResult, ResearchTarget]]:
        selected: list[tuple[SearchResult, ResearchTarget]] = []
        per_target_slots = max(1, self.max_sources // max(len(targets), 1))
        for target in targets:
            hits = results_by_target.get(target.id, [])
            for result in rerank(hits, target, top_k=per_target_slots):
                selected.append((result, target))
        return selected[: self.max_sources]

    def _collect_evidence(self, selected: list[tuple[SearchResult, ResearchTarget]]) -> list[Evidence]:
        evidence: list[Evidence] = []
        for result, target in selected[: self.max_documents]:
            self._append_document_evidence(evidence, result, target)
        for result, target in selected[self.max_documents : self.max_sources]:
            self._append_snippet_evidence(evidence, result, target)
        return evidence

    def _append_document_evidence(self, evidence: list[Evidence], result: SearchResult, target: ResearchTarget) -> None:
        _brand, model = target_identity(target)
        needles: tuple[str, ...] = tuple(_tokens(model))
        document = self._retrieve(result, needles)
        if document is None:
            self._append_snippet_evidence(evidence, result, target)
            return
        chunks = document_to_chunks(document, target, limit=self.max_chunks)
        content = " ".join(chunk.text for chunk in chunks[:1])[: self.max_chars]
        evidence.append(
            Evidence(
                source_type=source_for_result(result) or KnowledgeSourceType.WEB,
                source_name=document.source_name or _display_host(result.url),
                source_url=result.url,
                title=document.title or result.title,
                content=content or result.snippet,
                confidence=confidence_for_source(source_for_result(result)),
                kind=EvidenceKind.EXTRACTED,
            )
        )

    def _retrieve(self, result: SearchResult, needles: tuple[str, ...]) -> ResearchDocument | None:
        try:
            return self.retriever.retrieve(result.url, needles=needles, timeout_seconds=self.timeout_seconds)
        except Exception:
            return None

    def _append_snippet_evidence(self, evidence: list[Evidence], result: SearchResult, target: ResearchTarget) -> None:
        evidence.append(
            Evidence(
                source_type=source_for_result(result) or KnowledgeSourceType.WEB,
                source_name=_display_host(result.url),
                source_url=result.url,
                title=result.title,
                content=result.snippet,
                confidence=confidence_for_source(source_for_result(result)),
                kind=EvidenceKind.EXTRACTED,
            )
        )

    def _verdicts(self, evidence: list[Evidence], targets: list[ResearchTarget]) -> list[ClaimVerdict]:
        verdicts: list[ClaimVerdict] = []
        benchmark_groups: dict[str, list[Evidence]] = {}
        for item in evidence:
            for result in extract_geekbench(" ".join(part for part in (item.title, item.content) if part)):
                key = f"{result.benchmark_name} {result.benchmark_version or ''}".strip() + f" {result.score_type}"
                benchmark_groups.setdefault(key, []).append(item)
        for claim, items in benchmark_groups.items():
            model = targets[0].model or targets[0].name if targets else None
            verdicts.append(classify_evidence(items, claim=claim, target_model=model))
        if not verdicts and evidence:
            model = targets[0].model or targets[0].name if targets else None
            verdicts.append(
                classify_evidence(
                    evidence,
                    claim="información técnica del producto",
                    target_model=model,
                )
            )
        return verdicts

    def _build_context(self, evidence: list[Evidence], verdicts: list[ClaimVerdict]) -> str | None:
        if not evidence:
            return None
        lines = ["[Evidencia externa recopilada — usala SOLO como apoyo, no inventes datos]"]
        for verdict in verdicts:
            label = {"agreement": "apoya", "conflict": "CONFLICTO en", "variant_mismatch": "no aplica", "insufficient_evidence": "sin confirmar"}.get(verdict.verdict.value, verdict.verdict.value)
            lines.append(f"- {verdict.claim}: {label}")
        for item in evidence:
            lines.append(f"- {item.source_name}: {item.title or item.source_url}")
        context = "\n".join(lines)
        return context[: self.max_chars]

    def _note(self, queries_run: int, evidence: list[Evidence]) -> str:
        if evidence:
            return f"Investigación externa completada: {len(evidence)} fuente(s) en {queries_run} consulta(s)."
        return "No se encontró información externa adicional que respalde la consulta."


def _tokens(model: str | None) -> list[str]:
    if not model:
        return []
    return re.findall(r"[a-zA-Z0-9]+", model.casefold())