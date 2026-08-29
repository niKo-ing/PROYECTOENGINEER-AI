"""Expansión de términos para la búsqueda de productos.

Un usuario puede escribir "celulares" y esperar resultados que el
catálogo tiene categorizados como "Smartphones", o "notebooks" que
aparecen como "laptop". Esta expansión convierte la consulta libre en
el conjunto de términos equivalentes que deben coincidir contra el
nombre, la marca, el modelo o el nombre de la categoría de un producto.

Estrategia, por token normalizado:
1. Variantes singular/plural en español.
2. Si una variante pertenece a un grupo de sinónimos comercial, se suman
   todos los miembros del grupo.
3. Se descartan palabras vacías y tokens muy cortos.
"""

from __future__ import annotations


# Grupos de sinónimos comerciales. Solo términos de una palabra: el
# matcheo de categoría se hace contra palabras del catálogo real, y esta
# tabla cubre los equivalentes de uso cotidiano.
ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"celular", "celulares", "smartphone", "smartphones", "celu", "telefono", "telefonos"}),
    frozenset({"notebook", "notebooks", "laptop", "laptops", "portatil", "portatiles", "computador", "computadora", "computadores"}),
    frozenset({"monitor", "monitores", "pantalla", "pantallas"}),
    frozenset({"procesador", "procesadores", "cpu"}),
    frozenset({"grafica", "graficas", "gpu", "video"}),
    frozenset({"memoria", "rams", "ram"}),
    frozenset({"ssd", "solido"}),
    frozenset({"disco", "discos", "hd"}),
    frozenset({"teclado", "teclados", "keyboard", "keyboards"}),
    frozenset({"mouse", "raton", "ratones"}),
    frozenset({"audifono", "audifonos", "auricular", "auriculares", "headset", "headsets"}),
    frozenset({"camara", "camaras"}),
    frozenset({"parlante", "parlantes", "speaker", "speakers", "bocina", "bocinas"}),
    frozenset({"tv", "televisor", "televisores", "smarttv", "smarttvs"}),
    frozenset({"consola", "consolas", "playstation", "xbox", "nintendo", "switch"}),
    frozenset({"router", "routers", "enrutador", "enrutadores"}),
    frozenset({"tablet", "tablets", "ipad", "tableta", "tabletas"}),
    frozenset({"smartwatch", "smartwatches", "reloj", "relojes"}),
    frozenset({"silla", "sillas"}),
    frozenset({"fuente", "fuentes"}),
    frozenset({"gabinete", "gabinetes", "torre", "torres"}),
    frozenset({"impresora", "impresoras"}),
)

# Palabras vacías: palabras funcionales que no aportan a la búsqueda.
STOP_WORDS: frozenset[str] = frozenset({
    "para", "por", "de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas",
    "con", "sin", "en", "como", "que", "cual", "y", "o", "mi", "tu", "me", "te", "se",
    "busca", "busco", "buscar", "busqueda", "quiero", "necesito", "recomendame",
    "hay", "alguna", "alguno", "mejor", "buen", "decime", "cuales", "estos",
})

_ACCENTS: dict[str, str] = {
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
}
_ACCENT_TABLE = str.maketrans(_ACCENTS)


def normalize_spanish(term: str) -> str:
    """Lowercase y elimina tildes, para comparar términos sin acentos."""
    return term.casefold().translate(_ACCENT_TABLE)


def _flex_variants(term: str) -> set[str]:
    """Variantes singular/plural en español de un término normalizado."""
    variants = {term}
    if len(term) <= 3:
        return variants
    if term.endswith("es"):
        variants.add(term[:-1])
        variants.add(term[:-2])
    elif term.endswith("s"):
        variants.add(term[:-1])
    else:
        variants.add(term + "s")
        variants.add(term + "es")
    return variants


def expand_token(term: str) -> frozenset[str]:
    """Expande un token normalizado a su conjunto de términos equivalentes."""
    normalized = normalize_spanish(term)
    expanded: set[str] = set(_flex_variants(normalized))
    for variant in list(expanded):
        for group in ALIAS_GROUPS:
            if variant in group:
                expanded.update(group)
                break
    return frozenset(expanded)


def expand_query(query: str) -> list[frozenset[str]]:
    """Expande una consulta libre a una lista de conjuntos de términos.

    Cada conjunto corresponde a un token significativo de la consulta.
    Para el matcheo, cada token se resuelve con OR sobre sus términos y
    los tokens se combinan con AND.
    """
    grouped: list[frozenset[str]] = []
    seen: set[str] = set()
    for raw in query.split():
        token = normalize_spanish(raw).strip()
        if len(token) < 2 or token in STOP_WORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        grouped.append(expand_token(raw))
    return grouped