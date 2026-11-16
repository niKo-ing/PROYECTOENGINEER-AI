"""Dataset de pares etiquetados a partir del catálogo real (productos de Paris ingestados).

Las etiquetas salen de la identidad del producto (cada fila de ``products`` es un producto distinto):

* **positivo (1):** el mismo producto con el título «reescrito» como lo haría otra tienda (sin marca, orden distinto,
  abreviaturas, color o relleno comercial);
* **negativo difícil (0):** el mismo modelo con otra variante (otra capacidad/RAM) o otro modelo de la misma marca;
* **negativo fácil (0):** productos al azar.

La partición entrenamiento/prueba es **por producto** (un producto nunca aparece en ambos lados), para no inflar las métricas.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from ml.features import normalize, pair_features

FILLERS = ["oferta", "envio gratis", "garantia oficial", "libre", "nuevo", "original", "pack", "full"]
COLORS = ["negro", "azul", "gris", "plata", "blanco", "rojo", "verde", "dorado"]
ABBREV = [("pulgadas", "\""), ("notebook", "nb"), ("procesador", "cpu"), ("memoria", "ram"), ("celular", "smartphone"), ("smartphone", "celular")]


@dataclass(frozen=True)
class Pair:
    a: str
    b: str
    label: int
    product_a: int
    product_b: int
    kind: str


def typo(text: str, rng: random.Random) -> str:
    """Errata humana: una letra menos o dos letras cambiadas de lugar en una palabra larga."""
    words = text.split()
    candidates = [i for i, w in enumerate(words) if len(w) > 5]
    if not candidates:
        return text
    i = rng.choice(candidates)
    w = words[i]
    j = rng.randrange(1, len(w) - 2)
    words[i] = w[:j] + w[j + 1:] if rng.random() < 0.5 else w[:j] + w[j + 1] + w[j] + w[j + 2:]
    return " ".join(words)


def rewrite(title: str, rng: random.Random, noise: float = 0.35) -> str:
    """Cómo podría titular el mismo producto otra tienda (con ruido: erratas, datos que faltan, abreviaturas)."""
    words = title.split()
    if rng.random() < noise:  # la otra tienda no informa la capacidad o el color
        words = [w for w in words if not re.fullmatch(r"\d+\s*(GB|TB|gb|tb)", w) and rng.random() > 0.15 or not re.search(r"\d", w)] or words
    if rng.random() < noise / 2:  # «128 GB» pegado o «128G»
        words = [re.sub(r"(\d+)(GB|gb)", r"\1 \2", w) if rng.random() < 0.5 else re.sub(r"(\d+)(GB|gb)", r"\1G", w) for w in words]
    if len(words) > 3 and rng.random() < 0.5:
        words = words[1:]  # sin la marca / primer término
    if rng.random() < 0.5 and len(words) > 4:
        i = rng.randrange(1, len(words) - 1)
        words[i], words[i + 1] = words[i + 1], words[i]
    text = " ".join(words)
    if rng.random() < noise:
        text = typo(text, rng)
    for long, short in ABBREV:
        if rng.random() < 0.3:
            text = re.sub(long, short, text, flags=re.IGNORECASE)
    if rng.random() < 0.5:
        text = rng.choice(FILLERS) + " " + text
    return text.strip()


def variant(title: str, rng: random.Random) -> str | None:
    """El mismo modelo con otra capacidad o RAM (producto distinto). None si el título no tiene capacidades."""
    def bump(match: re.Match) -> str:
        n = int(match.group(1))
        options = [v for v in (4, 8, 16, 32, 64, 128, 256, 512, 1024) if v != n]
        return f"{rng.choice(options)}{match.group(2)}"

    new, count = re.subn(r"(\d+)\s*(GB|TB|gb|tb)\b", bump, title, count=1)
    return new if count and normalize(new) != normalize(title) else None


def recolor(title: str, rng: random.Random) -> str | None:
    """El mismo producto en otro color (SKU distinto). None si el título no menciona un color conocido."""
    from ml.features import COLOR_WORDS

    words = title.split()
    idx = [i for i, w in enumerate(words) if normalize(w).strip() in COLOR_WORDS]
    if not idx:
        return None
    current = normalize(words[idx[0]]).strip()
    words[idx[0]] = rng.choice([c for c in COLORS if c != current])
    return " ".join(words)


def build_pairs(products: list[tuple[int, str, str | None]], seed: int = 7, per_product: int = 4) -> list[Pair]:
    """``products``: (id, nombre, marca)."""
    rng = random.Random(seed)
    pairs: list[Pair] = []
    by_brand: dict[str, list[tuple[int, str]]] = {}
    for pid, name, brand in products:
        by_brand.setdefault((brand or "").lower(), []).append((pid, name))
    for pid, name, brand in products:
        for _ in range(per_product):
            pairs.append(Pair(name, rewrite(name, rng), 1, pid, pid, "positivo"))
        other = variant(name, rng)
        if other:
            pairs.append(Pair(name, rewrite(other, rng), 0, pid, pid, "negativo_variante"))
        recolored = recolor(name, rng)
        if recolored:
            pairs.append(Pair(name, rewrite(recolored, rng), 0, pid, pid, "negativo_color"))
        same_brand = [p for p in by_brand.get((brand or "").lower(), []) if p[0] != pid]
        for opid, oname in rng.sample(same_brand, min(2, len(same_brand))):
            pairs.append(Pair(name, rewrite(oname, rng), 0, pid, opid, "negativo_marca"))
        for opid, oname, _ in rng.sample(products, min(2, len(products))):
            if opid != pid:
                pairs.append(Pair(name, rewrite(oname, rng), 0, pid, opid, "negativo_azar"))
    return pairs


def split_by_product(pairs: list[Pair], test_fraction: float = 0.25, seed: int = 7) -> tuple[list[Pair], list[Pair]]:
    ids = sorted({p.product_a for p in pairs})
    random.Random(seed).shuffle(ids)
    test_ids = set(ids[: max(1, int(len(ids) * test_fraction))])
    train = [p for p in pairs if p.product_a not in test_ids and p.product_b not in test_ids]
    test = [p for p in pairs if p.product_a in test_ids and p.product_b in test_ids]
    return train, test


def to_matrix(pairs: list[Pair]):
    import numpy as np

    return np.array([pair_features(p.a, p.b) for p in pairs]), np.array([p.label for p in pairs])
