"""Fetch and normalize canonical specification pages.

The pipeline only reads the exact URLs registered in ``spec_sources``. Pages are
reduced to a compact plain-text context (specs table, ``#specs-list`` div or a
window around the target model) that the LLM is allowed to extract values from.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
FETCH_TIMEOUT_SECONDS = 30.0
STRIP_TAGS = ("script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg")
DEFAULT_WINDOW = 6000
DEFAULT_MAX_CHARS = 16000


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_text(element: object) -> str:
    text = element.get_text(" ", strip=True) if hasattr(element, "get_text") else str(element)
    return _collapse(text)


def _has_needle(text: str, needles: Iterable[str]) -> bool:
    haystack = unicodedata.normalize("NFKD", text.casefold())
    haystack = "".join(ch for ch in haystack if not unicodedata.combining(ch))
    return any(needle.casefold() in haystack for needle in needles)


_ALNUM = re.compile(r"[a-z0-9]")


def _is_model_token(needle: str) -> bool:
    return bool(re.search(r"\d", needle)) and " " not in needle and len(needle) >= 3


def _strong_match_count(text: str, needles: Iterable[str]) -> int:
    """Count needles that appear as a standalone alnum-median token (word boundaries)."""
    haystack = unicodedata.normalize("NFKD", text.casefold())
    haystack = "".join(ch for ch in haystack if not unicodedata.combining(ch))
    count = 0
    for needle in needles:
        if not _is_model_token(needle):
            continue
        n = needle.casefold()
        for match in re.finditer(re.escape(n), haystack):
            i, j = match.span()
            before_ok = i == 0 or not _ALNUM.match(haystack[i - 1])
            after_ok = j == len(haystack) or not _ALNUM.match(haystack[j])
            if before_ok and after_ok:
                count += 1
    return count


def _window_around(text: str, needles: Iterable[str], radius: int = DEFAULT_WINDOW, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    haystack = unicodedata.normalize("NFKD", text.casefold())
    haystack = "".join(ch for ch in haystack if not unicodedata.combining(ch))
    idx = -1
    for needle in needles:
        found = haystack.find(needle.casefold())
        if found >= 0 and (idx < 0 or found < idx):
            idx = found
    if idx < 0:
        return text[:max_chars]
    start = max(0, idx - radius)
    end = min(len(text), idx + radius)
    return text[start:end]


_TABLE_MAX_CHARS = 8000
_SPEC_SIGNAL = (
    "ghz", "mhz", " bit", "mb", "gb", "tdp", "core", "clock", "memory",
    "pipeline", "vram", " mm", "nm", "watt", "@",
)
_MIN_TABLE_DENSITY = 0.006


def _spec_density(text: str) -> float:
    count = 0
    for signal in _SPEC_SIGNAL:
        count += text.lower().count(signal)
    length = max(len(text), 1)
    return count / length


def normalize_context(html: str, needles: Iterable[str], *, prefer_text: bool = False) -> str:
    """Reduce a fetched page to the plain-text block documenting the target model."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()

    needles = tuple(needles)

    specs_list = soup.find(id="specs-list")
    if specs_list is not None:
        return _clean_text(specs_list)

    if not prefer_text:
        tables = [table for table in soup.find_all("table") if _has_needle(_clean_text(table), needles)]
        if tables:
            sized = [table for table in tables if len(_clean_text(table)) <= _TABLE_MAX_CHARS]
            pool = sized or tables
            best = max(
                pool,
                key=lambda table: (
                    _strong_match_count(_clean_text(table), needles),
                    _spec_density(_clean_text(table)),
                ),
            )
            candidate = _clean_text(best)
            if _spec_density(candidate) >= _MIN_TABLE_DENSITY:
                return candidate

    text = _clean_text(soup)
    if text:
        return _window_around(text, needles)
    return ""


def fetch_page(url: str) -> FetchedPage:
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en;q=0.8,es;q=0.7,*;q=0.5"},
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    return FetchedPage(url=url, html=response.text)


def fetch_context(url: str, needles: Iterable[str], *, prefer_text: bool = False) -> FetchedPage:
    page = fetch_page(url)
    return FetchedPage(url=url, html=normalize_context(page.html, needles, prefer_text=prefer_text))