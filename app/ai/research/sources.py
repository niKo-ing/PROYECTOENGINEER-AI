"""Source quality ranking for the Web Research pipeline.

Manufacturer-first: an official vendor documentation page outranks benchmarks,
which outrank curated reviews, which outrank generic web pages. Rank is generic
and not bound to any known brand, so it applies to any product researched.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from app.ai.evidence import KnowledgeSourceType

MANUFACTURER_HOSTS = (
    "apple.com",
    "samsung.com",
    "asus.com",
    "rog.asus.com",
    "lenovo.com",
    "hp.com",
    "dell.com",
    "acer.com",
    "msi.com",
    "xiaomi.com",
    "mi.com",
    "realme.com",
    "motorola.com",
    "lg.com",
    "sony.com",
    "nokia.com",
    "intel.com",
    "amd.com",
    "nvidia.com",
    "qualcomm.com",
    "mediatek.com",
)

BENCHMARK_HOSTS = (
    "geekbench.com",
    "browser.geekbench.com",
    "notebookcheck.net",
    "3dmark.com",
    "3dmark.benchmarks.ul.com",
    "benchmarks.ul.com",
    "passmark.com",
    "cpubenchmark.net",
    "videocardbenchmark.net",
    "anandtech.com",
    "spec.org",
    "opendata.geekbench.com",
)

_REVIEW_HOSTS = (
    "rtings.com",
    "techradar.com",
    "theverge.com",
    "techspot.com",
    "cnet.com",
    "pcmag.com",
    "tomshardware.com",
    "androidauthority.com",
    "gsmarena.com",
    "xataka.com",
)


def source_type_for_url(url: str | None) -> KnowledgeSourceType | None:
    """Best-effort classification of a URL into a knowledge source type."""
    if not url:
        return None
    host = _host(url)
    if host in MANUFACTURER_HOSTS or host.endswith(".asus.com"):
        return KnowledgeSourceType.MANUFACTURER
    if host in BENCHMARK_HOSTS:
        return KnowledgeSourceType.BENCHMARK
    if host in _REVIEW_HOSTS:
        return KnowledgeSourceType.REVIEW
    return KnowledgeSourceType.WEB


def source_priority(source_type: str | KnowledgeSourceType | None) -> int:
    """Higher is better. Manufacturer documentation outranks the rest."""
    if source_type is None:
        return 0
    if source_type == KnowledgeSourceType.CATALOG:
        return 60
    if source_type == KnowledgeSourceType.MANUFACTURER:
        return 50
    if source_type == KnowledgeSourceType.BENCHMARK:
        return 40
    if source_type == KnowledgeSourceType.REVIEW:
        return 30
    if source_type == KnowledgeSourceType.DOCUMENT:
        return 25
    return 20  # WEB


def confidence_for_source(source_type: str | KnowledgeSourceType | None) -> float:
    """A conservative confidence value per source rank (0..1)."""
    priority = source_priority(source_type)
    if priority >= 50:
        return 0.9
    if priority >= 40:
        return 0.8
    if priority >= 30:
        return 0.7
    return 0.5


def _host(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url.strip())
    host = (match.group(1) if match else url).lower()
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value


def variant_matches(target_model: str | None, text: Iterable[str], *, strict: bool = False) -> bool:
    """Check that ``text`` describes the exact variant of ``target_model``.

    Conservative matching rejects variant switches: a "POCO X6" target never
    matches "POCO X6 Pro", and an "iPhone 15 Pro" target never matches
    "iPhone 15". Harmless qualifiers (5G, storage, "global") are allowed.
    """
    target = _normalize(target_model or "")
    if not target:
        return False
    target_tokens = _tokens(target)
    if not target_tokens:
        return False

    haystack = " ".join(_normalize(part) for part in text)
    if not all(_word_boundary(haystack, token) for token in target_tokens):
        return False

    extra = sorted(set(_tokens(haystack)) - set(target_tokens))
    if any(token in _VARIANT_MARKERS for token in extra):
        return False
    if strict:
        token_diff = set(_tokens(haystack)) - set(target_tokens)
        if token_diff:
            return False
    return True


_VARIANT_MARKERS = {
    "pro", "promax", "plus", "mini", "max", "ultra", "super", "fe", "lite", "se",
    "ti", "evo", "xt", "b", "c", "e", "s", "slim", "elite", "gaming", "oc",
}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value))


def _word_boundary(haystack: str, token: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None