"""Pruebas unitarias del modelo de emparejamiento (características, decisión e interpretabilidad)."""

import pytest

from ml.features import FEATURE_NAMES, normalize, pair_features
from ml.model import THRESHOLD_MATCH, THRESHOLD_NO_MATCH


def feature(a, b, name):
    return pair_features(a, b)[FEATURE_NAMES.index(name)]


def test_normalize_removes_accents_and_glues_units():
    assert normalize("Índigo 128 GB") == "indigo 128gb"


def test_identical_titles_have_maximum_similarity():
    values = pair_features("Samsung Galaxy A54 128GB Negro", "Samsung Galaxy A54 128GB Negro")
    assert values[FEATURE_NAMES.index("ratio_secuencia")] == pytest.approx(1.0)
    assert len(values) == len(FEATURE_NAMES)


def test_capacity_conflict_is_detected():
    assert feature("iPhone 13 128GB Negro", "iPhone 13 256GB Negro", "capacidad_en_conflicto") == 1.0
    assert feature("iPhone 13 128GB Negro", "iPhone 13 128 GB Negro", "capacidad_igual") == 1.0


def test_color_conflict_is_detected():
    assert feature("Macbook Neo 256GB Indigo", "Macbook Neo 256GB Amarillo", "color_en_conflicto") == 1.0


def test_model_code_conflict():
    assert feature("Notebook Lenovo 15IAH8", "Notebook Lenovo 14ABR9", "modelo_en_conflicto") == 1.0


def test_model_matches_same_product_rewritten(match_model):
    r = match_model.predict("Samsung Galaxy A54 128GB Negro", "Celular Galaxy A54 5G 128 GB Negro")
    assert r["decision"] == "match" and r["probability"] >= THRESHOLD_MATCH


def test_model_rejects_other_variant_and_explains(match_model):
    r = match_model.predict("Apple iPhone 13 128GB Negro", "Apple iPhone 13 256GB Negro")
    assert r["decision"] == "no_match" and r["probability"] <= THRESHOLD_NO_MATCH
    assert any("capacidades" in reason for reason in r["reasons"])


def test_model_rejects_different_products(match_model):
    assert match_model.predict("Notebook Lenovo IdeaPad 3 15 8GB 512GB", "Smartphone Xiaomi Redmi Note 15 256GB")["decision"] == "no_match"


def test_batch_prediction_keeps_order_and_shape(match_model):
    results = match_model.predict_many([("a b c", "a b c"), ("zzz qqq", "iPhone 13 128GB")])
    assert len(results) == 2 and all({"decision", "probability", "reasons", "model_version"} <= set(r) for r in results)
