"""Características de un par de títulos de producto (¿son el mismo producto en dos tiendas?).

Se usan solo señales del texto, no el GTIN/MPN: el modelo sirve justo para los casos en que la tienda no los entrega
y el emparejador determinista (`app/catalog/matching.py`) queda en «ambiguo». Cada característica tiene nombre para
poder explicar la decisión (interpretabilidad para la toma de decisiones).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

FEATURE_NAMES = [
    "ratio_secuencia",       # similitud de caracteres (difflib)
    "jaccard_tokens",        # solapamiento de palabras
    "marca_igual",           # primer token «de marca» coincide
    "modelo_igual",          # tokens alfanuméricos con letras y dígitos (p. ej. «a54», «15iah8»)
    "modelo_en_conflicto",   # hay modelos distintos en ambos lados
    "numeros_en_comun",      # fracción de números compartidos (almacenamiento, RAM, pulgadas)
    "numeros_en_conflicto",  # números que solo aparecen en un lado (variante distinta)
    "capacidad_igual",       # GB/TB coinciden
    "capacidad_en_conflicto",
    "dif_longitud",          # diferencia relativa de largo
    "tokens_extra",          # palabras que aparecen solo en un título (relleno vs. variante)
    "color_en_conflicto",    # colores distintos: en el catálogo cada color es una oferta/SKU distinta
]

_STOP = {"de", "la", "el", "con", "para", "y", "en", "por", "los", "las", "un", "una", "color", "nuevo", "original"}
COLOR_WORDS = {"negro", "blanco", "azul", "gris", "plata", "plateado", "rojo", "verde", "dorado", "rosado", "rosa", "morado", "indigo", "amarillo", "celeste", "titanio", "grafito", "crema", "lila", "naranja", "cafe"}
_CAP = re.compile(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)\b")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"(\d)\s*(gb|tb)\b", r"\1\2", text)
    return re.sub(r"[^a-z0-9.+ ]+", " ", text)


def tokens(text: str) -> list[str]:
    return [t for t in normalize(text).split() if t and t not in _STOP]


def _models(toks: list[str]) -> set[str]:
    return {t for t in toks if re.search(r"[a-z]", t) and re.search(r"\d", t) and len(t) >= 3 and not _CAP.fullmatch(t)}


def _numbers(toks: list[str]) -> set[str]:
    return {t for t in toks if re.fullmatch(r"\d+(?:\.\d+)?", t)}


def _capacities(text: str) -> set[str]:
    return {f"{n.replace(',', '.')}{u}" for n, u in _CAP.findall(normalize(text))}


def _colors(toks: list[str]) -> set[str]:
    return {("plata" if t == "plateado" else t) for t in toks if t in COLOR_WORDS}


def pair_features(a: str, b: str) -> list[float]:
    ta, tb = tokens(a), tokens(b)
    sa, sb = set(ta), set(tb)
    union = sa | sb
    ma, mb = _models(ta), _models(tb)
    na, nb = _numbers(ta), _numbers(tb)
    ca, cb = _capacities(a), _capacities(b)
    return [
        SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio(),
        len(sa & sb) / len(union) if union else 0.0,
        float(bool(ta and tb and ta[0] == tb[0])),
        float(bool(ma and mb and ma & mb)),
        float(bool(ma and mb and not (ma & mb))),
        len(na & nb) / len(na | nb) if na | nb else 1.0,
        float(len(na ^ nb)),
        float(bool(ca and cb and ca == cb)),
        float(bool(ca and cb and ca != cb)),
        abs(len(a) - len(b)) / max(len(a), len(b), 1),
        float(len(sa ^ sb)),
        float(bool(_colors(ta) and _colors(tb) and _colors(ta) != _colors(tb))),
    ]
