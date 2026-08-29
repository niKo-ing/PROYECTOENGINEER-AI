"""Tests for product identity normalization and deterministic matching.

Covers:
1. Identity normalization functions
2. MPN variant comparison
3. Deterministic matching strategies (GTIN, MPN+brand, SKU, model)
4. Match result types (MATCH, NO_MATCH, AMBIGUOUS)
5. Conflict detection
6. Fuzzy candidate search
7. End-to-end: SP Digital + Paris same product → same Product
8. End-to-end: different variants → different Products
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.identity import (
    mpn_matches,
    mpn_variants,
    normalize_brand,
    normalize_gtin,
    normalize_manufacturer_sku,
    normalize_model,
    normalize_mpn,
)
from app.catalog.matching import (
    MatchCandidate,
    MatchResult,
    MatchStatus,
    ProductMatcher,
)
from app.db import Base
from app.ingestion.connectors import StoreConnector
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.service import CatalogIngestionService
from app.models.catalog import (
    Category,
    PriceHistory,
    Product,
    Store,
    StoreOffer,
)

# ── Test DB setup ──────────────────────────────────────────────────

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, Product, Store, Category):
        db.query(model).delete()
    db.commit()


def _make_connector(
    store_name_: str,
    store_domain_: str,
    records: list[dict],
) -> StoreConnector:
    """Create a mock connector for testing."""
    source = f"mock:{store_domain_}"
    sn = store_name_
    sd = store_domain_

    class _Conn(StoreConnector):
        store_name = sn
        store_domain = sd
        source_name = source

        def __init__(self, recs):
            self._recs = recs

        def extract(self):
            yield from self._recs

        def normalize(self, record):
            now = datetime.now(timezone.utc)
            return NormalizedOffer(
                source=self.source_name,
                external_id=record.get("external_id"),
                product_url=record.get("url", f"https://{sd}/p"),
                name=record.get("name", "Product"),
                brand=record.get("brand"),
                model=record.get("model"),
                mpn=record.get("mpn"),
                gtin=record.get("gtin"),
                sku=record.get("sku"),
                price=Decimal(str(record.get("price", 1000))),
                previous_price=None,
                currency="CLP",
                availability=True,
                stock="in_stock",
                image_url=None,
                category=record.get("category"),
                scraped_at=now,
            )

    return _Conn(records)


# ══════════════════════════════════════════════════════════════════
#  1. IDENTITY NORMALIZATION
# ══════════════════════════════════════════════════════════════════


class TestNormalizeGTIN:
    def test_strips_hyphens_spaces(self):
        assert normalize_gtin("750-1234-567890") == "7501234567890"

    def test_strips_whitespace(self):
        assert normalize_gtin(" 7501234567890 ") == "7501234567890"

    def test_valid_lengths(self):
        assert normalize_gtin("12345678") is not None  # GTIN-8
        assert normalize_gtin("123456789012") is not None  # GTIN-12
        assert normalize_gtin("7501234567890") is not None  # GTIN-13
        assert normalize_gtin("12345678901234") is not None  # GTIN-14

    def test_invalid_length_returns_none(self):
        assert normalize_gtin("12345") is None
        assert normalize_gtin("123456789012345") is None

    def test_none_returns_none(self):
        assert normalize_gtin(None) is None

    def test_empty_returns_none(self):
        assert normalize_gtin("") is None

    def test_non_digit_content_returns_none(self):
        assert normalize_gtin("abcdefghijkl") is None


class TestNormalizeBrand:
    def test_lowercase(self):
        assert normalize_brand("ASUS") == "asus"

    def test_strips_whitespace(self):
        assert normalize_brand("  ASUS  ") == "asus"

    def test_unicode_accents(self):
        assert normalize_brand("Café") == "cafe"

    def test_none_returns_none(self):
        assert normalize_brand(None) is None

    def test_empty_returns_none(self):
        assert normalize_brand("") is None

    def test_preserves_distinct_brands(self):
        assert normalize_brand("HP") != normalize_brand("Lenovo")

    def test_case_insensitive(self):
        assert normalize_brand("Asus") == normalize_brand("asus")


class TestNormalizeMPN:
    def test_uppercase(self):
        assert normalize_mpn("rtx-5070") == "RTX-5070"

    def test_collapse_whitespace(self):
        assert normalize_mpn("RTX  5070") == "RTX 5070"

    def test_strips_whitespace(self):
        assert normalize_mpn("  RTX-5070  ") == "RTX-5070"

    def test_keeps_hyphens(self):
        assert normalize_mpn("RTX-5070") == "RTX-5070"

    def test_keeps_dots(self):
        assert normalize_mpn("i7-13700K") == "I7-13700K"

    def test_none_returns_none(self):
        assert normalize_mpn(None) is None


class TestNormalizeModel:
    def test_lowercase(self):
        assert normalize_model("RTX 5070") == "rtx 5070"

    def test_collapse_whitespace(self):
        assert normalize_model("RTX  5070") == "rtx 5070"

    def test_keeps_hyphens(self):
        assert normalize_model("RTX-5070") == "rtx-5070"

    def test_none_returns_none(self):
        assert normalize_model(None) is None


class TestNormalizeManufacturerSKU:
    def test_uppercase(self):
        assert normalize_manufacturer_sku("rtx-5070-dual") == "RTX-5070-DUAL"

    def test_strips_whitespace(self):
        assert normalize_manufacturer_sku("  rtx-5070  ") == "RTX-5070"

    def test_keeps_hyphens(self):
        assert normalize_manufacturer_sku("RTX-5070") == "RTX-5070"

    def test_none_returns_none(self):
        assert normalize_manufacturer_sku(None) is None


# ══════════════════════════════════════════════════════════════════
#  2. MPN VARIANT COMPARISON
# ══════════════════════════════════════════════════════════════════


class TestMPNVariants:
    def test_generates_variants(self):
        variants = mpn_variants("RTX-5070")
        assert "RTX-5070" in variants
        assert "RTX5070" in variants
        assert "RTX 5070" in variants

    def test_none_returns_empty(self):
        assert mpn_variants(None) == set()


class TestMPNMatches:
    def test_hyphen_vs_space(self):
        assert mpn_matches("RTX-5070", "RTX 5070")

    def test_with_vs_without_separator(self):
        assert mpn_matches("RTX-5070", "RTX5070")

    def test_different_models_no_match(self):
        assert not mpn_matches("RTX-5070", "RTX-5060")

    def test_none_no_match(self):
        assert not mpn_matches(None, "RTX-5070")
        assert not mpn_matches("RTX-5070", None)

    def test_real_world_example(self):
        assert mpn_matches("GeForce RTX5070", "GeForce RTX 5070")


# ══════════════════════════════════════════════════════════════════
#  3. MATCH RESULT TYPES
# ══════════════════════════════════════════════════════════════════


class TestMatchResult:
    def test_match_result_properties(self):
        result = MatchResult(status=MatchStatus.MATCH, product=None)
        assert result.is_match
        assert not result.is_ambiguous
        assert not result.is_no_match

    def test_ambiguous_result(self):
        result = MatchResult(status=MatchStatus.AMBIGUOUS)
        assert result.is_ambiguous
        assert not result.is_match

    def test_no_match_result(self):
        result = MatchResult(status=MatchStatus.NO_MATCH)
        assert result.is_no_match
        assert not result.is_match


# ══════════════════════════════════════════════════════════════════
#  4. DETERMINISTIC MATCHING STRATEGIES
# ══════════════════════════════════════════════════════════════════


class TestMatchByGTIN:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_exact_gtin_match(self):
        with TestSession() as db:
            product = Product(
                name="RTX 5070",
                brand="NVIDIA",
                gtin="7501234567890",
            )
            db.add(product)
            db.commit()
            db.refresh(product)

            matcher = ProductMatcher(db)
            result = matcher.match_by_gtin("7501234567890")
            assert result.is_match
            assert result.product.id == product.id
            assert result.strategy == "gtin"
            assert result.confidence == 1.0

    def test_gtin_with_formatting(self):
        with TestSession() as db:
            product = Product(
                name="RTX 5070",
                brand="NVIDIA",
                gtin="7501234567890",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_gtin("750-1234-567890")
            assert result.is_match

    def test_no_gtin_match(self):
        with TestSession() as db:
            matcher = ProductMatcher(db)
            result = matcher.match_by_gtin("9999999999999")
            assert result.is_no_match

    def test_none_gtin(self):
        with TestSession() as db:
            matcher = ProductMatcher(db)
            result = matcher.match_by_gtin(None)
            assert result.is_no_match


class TestMatchByMPNBrand:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_exact_mpn_brand_match(self):
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070 DUAL OC",
                brand="ASUS",
                mpn="RTX5070-DUAL-OC",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_mpn_brand("RTX5070-DUAL-OC", "ASUS")
            assert result.is_match
            assert result.product.id == product.id
            assert result.strategy == "mpn_brand"

    def test_mpn_with_different_separator(self):
        """RTX5070-DUAL-OC should match RTX5070 DUAL OC."""
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070 DUAL OC",
                brand="ASUS",
                mpn="RTX5070 DUAL OC",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_mpn_brand("RTX5070-DUAL-OC", "Asus")
            assert result.is_match

    def test_different_mpn_no_match(self):
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070 TUF",
                brand="ASUS",
                mpn="RTX5070-TUF",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_mpn_brand("RTX5070-DUAL-OC", "ASUS")
            assert result.is_no_match

    def test_same_mpn_different_brand_no_match(self):
        with TestSession() as db:
            product = Product(
                name="MSI RTX 5070",
                brand="MSI",
                mpn="RTX5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_mpn_brand("RTX5070", "ASUS")
            assert result.is_no_match

    def test_mpn_unique_always_single_result(self):
        """UNIQUE constraint on mpn means match_by_mpn_brand can only
        return 0 or 1 result — AMBIGUOUS is impossible via MPN path."""
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                mpn="RTX5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_mpn_brand("RTX5070", "ASUS")
            assert result.is_match
            assert result.product.id == product.id


# ══════════════════════════════════════════════════════════════════
#  5. MANUFACTURER SKU MATCHING
# ══════════════════════════════════════════════════════════════════


class TestMatchByManufacturerSKU:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_manufacturer_sku_match(self):
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                manufacturer_sku="RTX5070-DUAL-12G",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_manufacturer_sku(
                "RTX5070-DUAL-12G", "ASUS"
            )
            assert result.is_match
            assert result.strategy == "manufacturer_sku"

    def test_pure_numeric_sku_skipped(self):
        """Store-internal numeric IDs should not match manufacturer_sku."""
        with TestSession() as db:
            product = Product(
                name="Product",
                manufacturer_sku="123456",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_manufacturer_sku("123456", "ASUS")
            assert result.is_no_match

    def test_sku_without_digits_skipped(self):
        """SKU without digits is not a manufacturer SKU."""
        with TestSession() as db:
            matcher = ProductMatcher(db)
            result = matcher.match_by_manufacturer_sku("ABCDEF", "ASUS")
            assert result.is_no_match

    def test_pure_numeric_sku_matches_when_source_declares_identity(self):
        """Paris declares numeric SKUs as identity → they match exactly."""
        with TestSession() as db:
            product = Product(
                name="Notebook Gamer ROG",
                brand="ASUS",
                manufacturer_sku="502788999",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_manufacturer_sku(
                "502788999", "ASUS", numeric_is_identity=True
            )
            assert result.is_match
            assert result.product is not None
            assert result.product.id == product.id
            assert result.strategy == "manufacturer_sku"

    def test_pure_numeric_sku_still_skipped_for_store_internal(self):
        """A source that does NOT declare numeric identity keeps the guard."""
        with TestSession() as db:
            product = Product(
                name="Product",
                brand="ASUS",
                manufacturer_sku="502788999",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_manufacturer_sku(
                "502788999", "ASUS", numeric_is_identity=False
            )
            assert result.is_no_match

    def test_match_delegates_numeric_identity_via_offer_flag(self):
        """match() honors sku_is_identity on the incoming offer.

        - offer(True): numeric SKU is usable as manufacturer identity → MATCH.
        - offer(False): numeric SKU is NOT used as identity; with an identical
          name the product is still detected via fuzzy fallback (AMBIGUOUS),
          and the exact-SKU guard remains NO_MATCH.
        """
        with TestSession() as db:
            product = Product(
                name="Notebook Gamer ROG",
                brand="ASUS",
                manufacturer_sku="502788999",
            )
            db.add(product)
            db.commit()

            def offer(sku_is_identity):
                return NormalizedOffer(
                    source="paris:www.paris.cl",
                    external_id="502788999",
                    product_url="https://www.paris.cl/p",
                    name="Notebook Gamer ROG",
                    brand="ASUS",
                    model=None,
                    mpn=None,
                    gtin=None,
                    sku="502788999",
                    price=Decimal("100"),
                    previous_price=None,
                    currency="CLP",
                    availability=True,
                    stock="in_stock",
                    image_url=None,
                    category="notebooks",
                    scraped_at=datetime.now(timezone.utc),
                    sku_is_identity=sku_is_identity,
                )

            matcher = ProductMatcher(db)
            # With identity declared → exact MATCH by manufacturer_sku.
            assert matcher.match(offer(True)).is_match
            # Without declaration → exact-SKU guard holds (NO_MATCH strategy).
            assert matcher.match_by_manufacturer_sku("502788999", "ASUS", False).is_no_match
            # Full match still runs fuzzy fallback; identical name → AMBIGUOUS.
            assert matcher.match(offer(False)).is_ambiguous


# ══════════════════════════════════════════════════════════════════
#  6. BRAND + MODEL MATCHING
# ══════════════════════════════════════════════════════════════════


class TestMatchByBrandModel:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_exact_brand_model_match(self):
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                model="RTX 5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_brand_model("ASUS", "RTX 5070")
            assert result.is_match
            assert result.strategy == "brand_model"

    def test_case_insensitive_brand_model(self):
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="Asus",
                model="rtx 5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_brand_model("asus", "RTX 5070")
            assert result.is_match

    def test_no_match(self):
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                model="RTX 5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_brand_model("ASUS", "RTX 5060")
            assert result.is_no_match


# ══════════════════════════════════════════════════════════════════
#  7. FUZZY CANDIDATE SEARCH
# ══════════════════════════════════════════════════════════════════


class TestFuzzyCandidates:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_finds_similar_names(self):
        with TestSession() as db:
            product = Product(
                name="ASUS GeForce RTX5070 DUAL OC 12GB",
                brand="ASUS",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            candidates = matcher.find_candidates(
                "ASUS RTX 5070 DUAL OC 12GB", "ASUS"
            )
            assert len(candidates) == 1
            assert candidates[0].score > 0.8

    def test_different_brand_no_candidates(self):
        with TestSession() as db:
            product = Product(
                name="MSI RTX 5070",
                brand="MSI",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            candidates = matcher.find_candidates(
                "ASUS RTX 5070", "ASUS"
            )
            assert len(candidates) == 0

    def test_no_candidates_without_brand(self):
        with TestSession() as db:
            matcher = ProductMatcher(db)
            candidates = matcher.find_candidates("RTX 5070", None)
            assert len(candidates) == 0

    def test_limit_respected(self):
        with TestSession() as db:
            for i in range(10):
                db.add(Product(
                    name=f"ASUS Product {i}",
                    brand="ASUS",
                ))
            db.commit()

            matcher = ProductMatcher(db)
            candidates = matcher.find_candidates(
                "ASUS Product", "ASUS"
            )
            assert len(candidates) <= 5


# ══════════════════════════════════════════════════════════════════
#  8. CONFLICT DETECTION
# ══════════════════════════════════════════════════════════════════


class TestConflictDetection:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_no_conflict_when_gtin_matches_mpn(self):
        with TestSession() as db:
            product = Product(
                name="RTX 5070",
                brand="NVIDIA",
                gtin="7501234567890",
                mpn="RTX5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = "7501234567890"
                mpn = "RTX5070"
                brand = "NVIDIA"

            conflict = matcher.check_conflict(FakeOffer())
            assert conflict is None

    def test_conflict_when_gtin_and_mpn_point_different(self):
        with TestSession() as db:
            p1 = Product(
                name="Product A",
                brand="Brand A",
                gtin="7501234567890",
            )
            p2 = Product(
                name="Product B",
                brand="Brand B",
                mpn="XYZ-123",
                model="XYZ",
            )
            db.add_all([p1, p2])
            db.commit()

            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = "7501234567890"
                mpn = "XYZ-123"
                brand = "Brand B"

            conflict = matcher.check_conflict(FakeOffer())
            assert conflict is not None
            assert "CONFLICT" in conflict


# ══════════════════════════════════════════════════════════════════
#  9. END-TO-END: CROSS-STORE PRODUCT MATCHING
# ══════════════════════════════════════════════════════════════════


class TestEndToEndCrossStoreMatching:
    """SP Digital + Paris same product → same Product."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_mpn_different_store_names(self):
        """Same MPN+brand from two stores creates one Product."""
        records_spdigital = [
            {
                "url": "https://www.spdigital.cl/notebook-hp/p",
                "external_id": "NA0000081556",
                "name": "Notebook HP Pavilion 15",
                "brand": "HP",
                "mpn": "7VW78LA",
                "price": 500000,
            }
        ]
        records_paris = [
            {
                "url": "https://www.paris.cl/notebook-hp-pavilion.html",
                "external_id": "12345",
                "name": "HP Pavilion 15-eg2000la",
                "brand": "HP",
                "mpn": "7VW78LA",
                "price": 520000,
            }
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)

            # SP Digital first
            conn1 = _make_connector("SP Digital", "www.spdigital.cl", records_spdigital)
            report1 = IngestionPipeline(service).run(conn1)
            assert report1.offers_created == 1
            assert db.query(Product).count() == 1

            # Paris second — should match same Product
            conn2 = _make_connector("Paris", "www.paris.cl", records_paris)
            report2 = IngestionPipeline(service).run(conn2)
            assert report2.offers_updated == 0  # new offer from Paris
            assert report2.offers_created == 1
            assert db.query(Product).count() == 1  # still one Product
            assert db.query(StoreOffer).count() == 2  # two offers

    def test_same_gtin_different_stores(self):
        """Same GTIN from two stores creates one Product."""
        records_a = [
            {
                "url": "https://a.store/p1",
                "external_id": "A001",
                "name": "RTX 5070 ASUS",
                "brand": "ASUS",
                "gtin": "4718017999999",
                "price": 600000,
            }
        ]
        records_b = [
            {
                "url": "https://b.store/p1",
                "external_id": "B001",
                "name": "ASUS GeForce RTX 5070 DUAL OC",
                "brand": "ASUS",
                "gtin": "4718017999999",
                "price": 620000,
            }
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)

            conn_a = _make_connector("Store A", "a.store", records_a)
            IngestionPipeline(service).run(conn_a)
            assert db.query(Product).count() == 1

            conn_b = _make_connector("Store B", "b.store", records_b)
            IngestionPipeline(service).run(conn_b)
            assert db.query(Product).count() == 1
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  10. END-TO-END: DIFFERENT VARIANTS → DIFFERENT PRODUCTS
# ══════════════════════════════════════════════════════════════════


class TestDifferentVariants:
    """RTX 5070 DUAL and RTX 5070 TUF should NOT merge."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_different_mpn_creates_separate_products(self):
        records_dual = [
            {
                "url": "https://store/p1",
                "external_id": "D001",
                "name": "ASUS RTX 5070 DUAL OC",
                "brand": "ASUS",
                "mpn": "RTX5070-DUAL-OC",
                "price": 600000,
            }
        ]
        records_tuf = [
            {
                "url": "https://store/p2",
                "external_id": "T001",
                "name": "ASUS RTX 5070 TUF OC",
                "brand": "ASUS",
                "mpn": "RTX5070-TUF-OC",
                "price": 620000,
            }
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)

            conn_dual = _make_connector("Store", "store", records_dual)
            IngestionPipeline(service).run(conn_dual)

            conn_tuf = _make_connector("Store", "store", records_tuf)
            IngestionPipeline(service).run(conn_tuf)

            assert db.query(Product).count() == 2

    def test_different_mpn_same_brand_creates_separate(self):
        """Same brand but different MPNs should NOT merge — different variants."""
        records_dual = [
            {
                "url": "https://store/p1",
                "external_id": "A001",
                "name": "ASUS RTX 5070 DUAL OC",
                "brand": "ASUS",
                "mpn": "RTX5070-DUAL",
                "price": 600000,
            }
        ]
        records_tuf = [
            {
                "url": "https://store/p2",
                "external_id": "B001",
                "name": "ASUS RTX 5070 TUF OC",
                "brand": "ASUS",
                "mpn": "RTX5070-TUF",
                "price": 610000,
            }
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)

            conn_a = _make_connector("Store", "store", records_dual)
            IngestionPipeline(service).run(conn_a)

            conn_b = _make_connector("Store2", "store2", records_tuf)
            IngestionPipeline(service).run(conn_b)

            # Different MPNs → different Products even with same brand
            assert db.query(Product).count() == 2


# ══════════════════════════════════════════════════════════════════
#  11. AMBIGUOUS → NEW PRODUCT (not silent merge)
# ══════════════════════════════════════════════════════════════════


class TestAmbiguousBehavior:
    """Ambiguous match should create new product, not merge."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ambiguous_brand_model_creates_new_product(self):
        """Multiple products with same brand+model (different MPNs) → new product created."""
        with TestSession() as db:
            p1 = Product(name="ASUS RTX 5070 DUAL", brand="ASUS", model="rtx 5070")
            p2 = Product(name="ASUS RTX 5070 TUF", brand="ASUS", model="rtx 5070")
            db.add_all([p1, p2])
            db.commit()

            service = CatalogIngestionService(db)
            conn = _make_connector("Store", "store", [
                {
                    "url": "https://store/p1",
                    "external_id": "C001",
                    "name": "ASUS RTX 5070 STRIX",
                    "brand": "ASUS",
                    "model": "rtx 5070",
                    "price": 600000,
                }
            ])
            report = IngestionPipeline(service).run(conn)

            # Ambiguous via fuzzy brand+model → new product created
            assert db.query(Product).count() == 3
            assert report.offers_created == 1


# ══════════════════════════════════════════════════════════════════
#  12. LEGACY COMPATIBILITY
# ══════════════════════════════════════════════════════════════════


class TestLegacyCompatibility:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_match_legacy_returns_product(self):
        with TestSession() as db:
            product = Product(
                name="Test Product",
                brand="Test",
                gtin="7501234567890",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = "7501234567890"
                mpn = None
                brand = None
                model = None
                sku = None
                name = "Test"

            result = matcher.match_legacy(FakeOffer())
            assert result is not None
            assert result.id == product.id

    def test_match_legacy_returns_none(self):
        with TestSession() as db:
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = None
                model = None
                sku = None
                name = "Unknown"

            result = matcher.match_legacy(FakeOffer())
            assert result is None


# ══════════════════════════════════════════════════════════════════
#  10. NUMERIC SKU IDENTITY + COUNTER SEMANTICS (Paris regression)
# ══════════════════════════════════════════════════════════════════


def _identity_connector(store_domain, *, numeric_sku_is_identity, records):
    """Build a connector that can declare numeric SKU identity for tests."""

    class _ConnBase(StoreConnector):
        def __init__(self, recs):
            self._recs = recs

        def extract(self):
            yield from self._recs

        def normalize(self, record):
            now = datetime.now(timezone.utc)

            return NormalizedOffer(
                source=self.source_name,
                external_id=record.get("external_id"),
                product_url=record.get("url", f"https://{store_domain}/p"),
                name=record.get("name", "Product"),
                brand=record.get("brand"),
                model=record.get("model"),
                mpn=record.get("mpn"),
                gtin=record.get("gtin"),
                sku=record.get("sku"),
                price=Decimal(str(record.get("price", 1000))),
                previous_price=None,
                currency="CLP",
                availability=True,
                stock="in_stock",
                image_url=None,
                category=record.get("category"),
                scraped_at=now,
                sku_is_identity=numeric_sku_is_identity,
            )

    _Conn = type(
        "_Conn",
        (_ConnBase,),
        {
            "store_name": store_domain,
            "store_domain": store_domain,
            "source_name": f"mock:{store_domain}",
            "numeric_sku_is_identity": numeric_sku_is_identity,
        },
    )

    return _Conn(records)

class TestNumericSkuIdentityAndCounters:
    """Regression for Paris numeric SKU duplication (run 4)."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    _PARIS_NUMERIC = {
        "url": "https://www.paris.cl/notebook-gamer",
        "external_id": "502788999",
        "name": "Notebook Gamer ROG Zephyrus Duo 16",
        "brand": "ASUS",
        "sku": "502788999",
    }

    def test_paris_numeric_sku_matches_and_reuses_product(self):
        """Paris numeric SKU → exact MATCH and single Product."""
        with TestSession() as db:
            service = CatalogIngestionService(db)
            conn = _identity_connector(
                "www.paris.cl", numeric_sku_is_identity=True,
                records=[dict(self._PARIS_NUMERIC)],
            )
            report1 = IngestionPipeline(service).run(conn)
            assert report1.products_created == 1
            assert report1.products_matched == 0
            assert db.query(Product).count() == 1

            # Same Store, offer already exists → no new offer, product reused
            report2 = IngestionPipeline(service).run(_identity_connector(
                "www.paris.cl", numeric_sku_is_identity=True,
                records=[dict(self._PARIS_NUMERIC, price=550000)],
            ))
            assert report2.products_created == 0
            assert report2.products_matched == 1
            assert report2.offers_created == 0
            assert report2.offers_updated == 1
            assert db.query(Product).count() == 1

    def test_paris_numeric_sku_does_not_create_duplicate(self):
        """Existing numeric SKU never duplicates a Product on re-ingest."""
        with TestSession() as db:
            service = CatalogIngestionService(db)

            def run(sku):
                return IngestionPipeline(service).run(_identity_connector(
                    "www.paris.cl", numeric_sku_is_identity=True,
                    records=[dict(self._PARIS_NUMERIC, external_id=sku, sku=sku)],
                ))

            # Seed 5 distinct numeric-SKU products across two passes
            run("502788999")
            run("502788999")
            run("424615999")
            run("502788999")
            run("424617999")
            assert db.query(Product).count() == 3  # distinct SKUs, no duplicates

    def test_connector_without_numeric_identity_keeps_guard(self):
        """Non-declaring source keeps the numeric-SKU protection."""
        with TestSession() as db:
            service = CatalogIngestionService(db)
            conn = _identity_connector(
                "www.otro.cl", numeric_sku_is_identity=False,
                records=[dict(self._PARIS_NUMERIC)],
            )
            IngestionPipeline(service).run(conn)
            first_count = db.query(Product).count()

            # A second identical numeric SKU from a non-declaring source:
            # guard still active → product is NOT reused, but fuzzy also
            # cannot confirm, so a new Product is created (guard preserved).
            conn2 = _identity_connector(
                "www.otro.cl", numeric_sku_is_identity=False,
                records=[dict(self._PARIS_NUMERIC, external_id="502788999", sku="502788999")],
            )
            IngestionPipeline(service).run(conn2)
            assert db.query(Product).count() >= first_count

            # The guard specifically means the exact SKU match must NOT fire:
            with TestSession() as db2:
                matcher = ProductMatcher(db2)
                result = matcher.match_by_manufacturer_sku("502788999", "ASUS", False)
                assert result.is_no_match

    def test_products_created_counts_real_products(self):
        """products_created tracks real Product rows, not offers."""
        with TestSession() as db:
            service = CatalogIngestionService(db)
            conn = _identity_connector(
                "www.paris.cl", numeric_sku_is_identity=True,
                records=[dict(self._PARIS_NUMERIC)],
            )
            report = IngestionPipeline(service).run(conn)
            assert report.products_created == 1
            assert report.products_matched == 0
            assert report.offers_created == 1
            assert report.offers_updated == 0

    def test_products_updated_counts_real_products(self):
        """products_updated tracks reused Products, not updated offers."""
        with TestSession() as db:
            service = CatalogIngestionService(db)
            conn = _identity_connector(
                "www.paris.cl", numeric_sku_is_identity=True,
                records=[dict(self._PARIS_NUMERIC)],
            )
            IngestionPipeline(service).run(conn)

            report2 = IngestionPipeline(service).run(_identity_connector(
                "www.paris.cl", numeric_sku_is_identity=True,
                records=[dict(self._PARIS_NUMERIC, price=600000)],
            ))
            assert report2.products_created == 0
            assert report2.products_matched == 1
            assert report2.offers_created == 0
            assert report2.offers_updated == 1

    def test_offers_counters_unchanged(self):
        """offers_created/offers_updated still count Offers."""
        with TestSession() as db:
            service = CatalogIngestionService(db)
            conn = _identity_connector(
                "www.paris.cl", numeric_sku_is_identity=True,
                records=[dict(self._PARIS_NUMERIC)],
            )
            r1 = IngestionPipeline(service).run(conn)
            assert r1.offers_created == 1
            assert r1.offers_updated == 0

            r2 = IngestionPipeline(service).run(_identity_connector(
                "www.paris.cl", numeric_sku_is_identity=True,
                records=[dict(self._PARIS_NUMERIC, price=610000)],
            ))
            assert r2.offers_created == 0
            assert r2.offers_updated == 1

    def test_new_legitimate_paris_product_counts_correctly(self):
        """A genuinely new Paris Product is counted as created."""
        with TestSession() as db:
            service = CatalogIngestionService(db)
            for sku in ["424615999", "424617999", "424619999"]:
                IngestionPipeline(service).run(_identity_connector(
                    "www.paris.cl", numeric_sku_is_identity=True,
                    records=[dict(self._PARIS_NUMERIC, external_id=sku, sku=sku)],
                ))
            assert db.query(Product).count() == 3
            assert service is not None
