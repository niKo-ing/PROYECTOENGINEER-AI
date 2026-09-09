import { fetchCategories } from "@/lib/api/categories";
import { sendChatMessage, type ChatResult, type ChatTurn } from "@/lib/api/chat";
import { fetchOffers, fetchPriceHistory } from "@/lib/api/offers";
import { fetchProduct, searchProducts } from "@/lib/api/products";
import type { CategoryRead } from "@/types/category";
import type { StoreOfferRead, PriceHistoryRead } from "@/types/offer";
import type { ProductRead } from "@/types/product";
import { availabilityLabel, formatCLP, formatDate } from "@/lib/utils";

export type CatalogIntent =
  | "search"
  | "cheapest"
  | "compare"
  | "offers"
  | "price_history"
  | "best_value"
  | "single_product";

export interface CatalogReference {
  id: number;
  name: string;
  category: string;
  brand: string | null;
  lowest_price: number | null;
  lowest_price_store: string | null;
  rating: number | null;
}

export interface CatalogContext {
  detected: boolean;
  intent: CatalogIntent | null;
  query: string | null;
  references: CatalogReference[];
  products: ProductRead[];
  statements: string[];
  missing: boolean;
}

export interface OrchestratedChatResult extends ChatResult {
  catalog: CatalogContext;
}

const INTENT_PATTERNS: Array<{ intent: Exclude<CatalogIntent, "single_product">; patterns: string[] }> = [
  {
    intent: "best_value",
    patterns: [
      "buen precio",
      "a buen precio",
      "precio/rating",
      "precio rating",
      "relacion precio/rating",
      "relacion precio",
      "mejor rating",
      "vale la pena",
      "relacion precio/calidad",
    ],
  },
  {
    intent: "cheapest",
    patterns: [
      "donde esta mas barat",
      "donde venden mas barat",
      "el mas barat",
      "la mas barat",
      "lo mas barat",
      "mas barat",
      "menor precio",
      "precio mas bajo",
      "mas econom",
    ],
  },
  {
    intent: "offers",
    patterns: [
      "ofertas",
      "oferta",
      "donde lo venden",
      "donde venden",
      "donde lo tienen",
      "donde comprar",
      "en que tienda",
      "que tienda",
      "que tiendas",
    ],
  },
  {
    intent: "price_history",
    patterns: [
      "historial",
      "historico",
      "evolucion del precio",
      "como ha cambiado el precio",
      "ha cambiado el precio",
      "cambio de precio",
      "cuanto costaba",
      "cuanto valia",
      "cuanto era el precio",
      "subio el precio",
      "subio de precio",
      "bajo el precio",
      "bajo de precio",
      "el precio era",
      "ha subido",
      "ha bajado",
      "como esta el precio",
      "mantenido el precio",
    ],
  },
  {
    intent: "compare",
    patterns: ["compara", "comparar", "comparacion", "cual es mejor", "cual conviene", "que conviene", "mejor opcion", "entre estos", "mejor compra"],
  },
];

const PRODUCT_TERMS = [
  "tarjeta grafica",
  "tarjeta de video",
  "memoria ram",
  "smartphone",
  "computador",
  "televisor",
  "audifonos",
  "procesador",
  "impresora",
  "consola",
  "teclado",
  "parlante",
  "monitor",
  "notebook",
  "laptop",
  "celular",
  "telefono",
  "telefonos",
  "tablet",
  "iphone",
  "galaxy",
  "macbook",
  "playstation",
  "redmi",
  "gaming",
  "gamer",
  "asus",
  "lenovo",
  "samsung",
  "xiaomi",
  "apple",
  "ssd",
  "mouse",
  "poco",
  "ipad",
  "xbox",
  "tv",
  "hp",
  "acer",
  "motorola",
  "lg",
  "sony",
  "dell",
  "msi",
  "realme",
  "nokia",
];

const BRAND_TERMS = ["asus", "lenovo", "samsung", "xiaomi", "apple", "hp", "acer", "motorola", "lg", "sony", "dell", "msi", "realme", "nokia"];
const MODEL_TERMS = ["galaxy", "iphone", "ipad", "macbook", "redmi", "poco", "playstation", "xbox"];

const SEARCH_VERBS = [
  "buscame",
  "busca ",
  "busco",
  "buscar",
  "buscando",
  "buscas",
  "necesito",
  "quiero",
  "recomendame",
  "recomiendame",
  "recomiendame",
  "muestrame",
  "mostrame",
  "insename",
  "ensename",
  "contame",
  "hay algun",
  "hay algo",
  "que producto",
  "que productos",
  "quisiera",
];

const PRODUCT_REFERENCE_WORDS = ["este producto", "el producto", "ese producto", "de ese producto", "sobre este", "de este producto"];

const ACCENTS: Record<string, string> = {
  "á": "a",
  "é": "e",
  "í": "i",
  "ó": "o",
  "ú": "u",
  "ü": "u",
  "ñ": "n",
};

const INTENT_LABELS: Record<CatalogIntent, string> = {
  search: "búsqueda de productos",
  cheapest: "cuál es más barato",
  compare: "comparación de productos",
  offers: "ofertas disponibles",
  price_history: "historial de precios",
  best_value: "relación precio/valor",
  single_product: "consulta sobre un producto específico",
};

function normalize(value: string): string {
  return value.toLowerCase().replace(/[áéíóúüñ]/g, (character) => ACCENTS[character] ?? character);
}

export function detectIntent(message: string, productId: number | null | undefined): { intent: CatalogIntent | null; terms: string[] } {
  const normalized = normalize(message);
  const hasProductScope = Boolean(productId);

  for (const group of INTENT_PATTERNS) {
    const matched = group.patterns.find((pattern) => normalized.includes(pattern));
    if (matched) {
      return { intent: group.intent, terms: matched.split(" ").filter((term) => term.length >= 3) };
    }
  }

  const presentTerms = PRODUCT_TERMS.filter((term) => normalized.includes(term));
  const hasProductTerm = presentTerms.length > 0;
  const hasSearchVerb = SEARCH_VERBS.some((verb) => normalized.includes(verb));
  const referencesCurrentProduct = hasProductScope && PRODUCT_REFERENCE_WORDS.some((word) => normalized.includes(word));

  if (hasProductTerm || hasSearchVerb || referencesCurrentProduct) {
    return { intent: hasProductScope ? "single_product" : "search", terms: presentTerms };
  }

  return { intent: null, terms: [] };
}

function pickQueryTerm(terms: string[]): string | null {
  if (terms.length === 0) return null;
  const brand = BRAND_TERMS.filter((term) => terms.includes(term)).slice(-1)[0];
  if (brand) return brand;
  const model = MODEL_TERMS.filter((term) => terms.includes(term)).slice(-1)[0];
  if (model) return model;
  return terms.reduce((longest, term) => (term.length > longest.length ? term : longest));
}

function matchCategory(message: string, categories: CategoryRead[]): CategoryRead | null {
  const normalized = normalize(message);
  const synonyms: Record<string, string[]> = {
    notebooks: ["notebook", "laptop", "computador", "gamer", "gaming", "pc"],
    celulares: ["celular", "smartphone", "iphone", "galaxy", "redmi", "poco", "telefono"],
  };
  for (const category of categories) {
    const key = normalize(category.name);
    const mapped = synonyms[key];
    if (!mapped) continue;
    if (mapped.some((word) => normalized.includes(word))) {
      return category;
    }
  }
  return null;
}

function toReference(product: ProductRead): CatalogReference {
  return {
    id: product.id,
    name: product.name,
    category: product.category,
    brand: product.brand,
    lowest_price: product.lowest_price,
    lowest_price_store: product.lowest_price_store,
    rating: product.rating,
  };
}

function productStatement(product: ProductRead): string {
  const rating = product.rating !== null && product.rating !== undefined ? ` | Rating: ${product.rating.toFixed(1)}` : "";
  const price =
    product.lowest_price !== null && product.lowest_price !== undefined
      ? ` | Precio desde ${formatCLP(product.lowest_price)}${product.lowest_price_store ? ` en ${product.lowest_price_store}` : ""}`
      : " | Sin precios cargados";
  const offers = product.offer_count > 0 ? ` | ${product.offer_count} oferta${product.offer_count === 1 ? "" : "s"}` : "";
  return `Producto #${product.id}: "${product.name}" — Marca ${product.brand ?? "no especificada"} | Categoría ${product.category}${rating}${price}${offers} | Ficha: /product/${product.id}`;
}

function offersStatement(productId: number, offers: StoreOfferRead[]): string {
  const header = `Ofertas de #${productId} (via /api/v1/products/${productId}/offers):`;
  if (offers.length === 0) {
    return `${header}\n  • Sin ofertas cargadas en la API.`;
  }
  const lines = offers.slice(0, 4).map((offer) => {
    const original = offer.original_price !== null && offer.original_price !== undefined ? ` (antes ${formatCLP(offer.original_price)})` : "";
    return `  • ${offer.store.name} — ${formatCLP(offer.price)}${original} — ${availabilityLabel(offer.stock_status, offer.availability)} — ${offer.url}`;
  });
  return `${header}\n${lines.join("\n")}`;
}

function historyStatement(productId: number, history: PriceHistoryRead[]): string {
  const header = `Historial de precios de #${productId} (via /api/v1/products/${productId}/price-history):`;
  if (history.length === 0) {
    return `${header}\n  • Sin historial de precios en la API.`;
  }
  const lines = history.slice(-10).map((entry) => `  • ${formatDate(entry.observed_at)} — ${formatCLP(entry.price)}`);
  return `${header}\n${lines.join("\n")}`;
}

function needsOffers(intent: CatalogIntent | null): boolean {
  return intent === "cheapest" || intent === "compare" || intent === "offers" || intent === "best_value";
}

function needsHistory(intent: CatalogIntent | null): boolean {
  return intent === "price_history" || intent === "best_value" || intent === "compare";
}

export async function buildCatalogContext(
  message: string,
  options: { productId?: number | null; forceProductScope?: boolean } = {},
): Promise<CatalogContext> {
  const { productId, forceProductScope } = options;
  const { intent, terms } = detectIntent(message, productId);

  const productScope = forceProductScope || (Boolean(productId) && intent !== null);
  if (!productScope && intent === null) {
    return { detected: false, intent: null, query: null, references: [], products: [], statements: [], missing: false };
  }

  const statements: string[] = [];
  const references: CatalogReference[] = [];
  const products: ProductRead[] = [];
  let missing = false;

  if (productScope && Boolean(productId)) {
    try {
      const [product, offers, history] = await Promise.all([
        fetchProduct(productId!),
        fetchOffers(productId!),
        fetchPriceHistory(productId!),
      ]);
      products.push(product);
      references.push(toReference(product));
      statements.push(productStatement(product));
      statements.push(offersStatement(product.id, offers));
      statements.push(historyStatement(product.id, history));
    } catch {
      missing = true;
      statements.push(`No pude obtener datos del producto #${productId} desde la API.`);
    }
    return { detected: true, intent: intent ?? "single_product", query: null, references, products, statements, missing };
  }

  const candidates = intent === "search" ? terms : terms.length > 0 ? terms : [];
  const query = pickQueryTerm(candidates);
  if (!query) {
    missing = true;
    statements.push("No pude identificar un producto concreto en tu consulta para consultar el catálogo. Pedí que lo especifique.");
    return { detected: true, intent: intent ?? "search", query: null, references, products, statements, missing };
  }

  try {
    const [categories, searchResult] = await Promise.all([fetchCategories(), searchProducts({ query, limit: 6 })]);
    const category = matchCategory(message, categories);
    const categoryFiltered =
      category && !searchResult.items.some((item) => normalize(item.category).includes(normalize(category.name)))
        ? await searchProducts({ query, category: category.name, limit: 6 })
        : searchResult.items.length === 0
          ? await searchProducts({ query, category: category?.name, limit: 6 })
          : null;

    const items = categoryFiltered && categoryFiltered.items.length > 0 ? categoryFiltered.items : searchResult.items;
    products.push(...items);
    references.push(...items.map(toReference));

    if (items.length === 0) {
      missing = true;
      statements.push(`La búsqueda "${query}" no devolvió productos desde /api/v1/products.`);
    } else {
      statements.push(items.map(productStatement).join("\n"));
    }

    const targets = items.slice(0, 3);
    const enrich = [];
    if (needsOffers(intent)) {
      enrich.push(...targets.map((product) => fetchOffers(product.id).then((offers) => offersStatement(product.id, offers))));
    }
    if (needsHistory(intent)) {
      enrich.push(...targets.slice(0, 2).map((product) => fetchPriceHistory(product.id).then((history) => historyStatement(product.id, history))));
    }
    if (enrich.length > 0) {
      const resolved = await Promise.all(enrich);
      statements.push(...resolved);
    }
    return { detected: true, intent: intent ?? "search", query, references, products, statements, missing };
  } catch {
    missing = true;
    statements.push("El catálogo no está disponible en este momento.");
    return { detected: true, intent: intent ?? "search", query, references, products, statements, missing };
  }
}

function composePrompt(context: CatalogContext, message: string): string {
  const intro = [
    "[CONTEXTO DE CATÁLOGO SOLOTODO — datos reales obtenidos de la API en tiempo real, no inventados]",
    `Intención detectada: ${context.intent ? INTENT_LABELS[context.intent] : "catálogo"}`,
  ];
  if (context.query) {
    intro.push(`Búsqueda usada contra /api/v1/products: "${context.query}"`);
  }
  const instructions = [
    "Respondé en español usando SOLO los datos de este contexto o los devueltos por los tools del catálogo.",
    "Si un dato (precio, tienda, rating, ofertas, historial) no aparece, decí que no está disponible en la API.",
    "No inventes productos, precios, tiendas, ratings ni historial.",
    "Si nombrás un producto, citá su enlace /product/{id}.",
  ];
  return [...intro, "", ...context.statements, "", ...instructions, "", `Pregunta del usuario: ${message}`].join("\n");
}

export async function sendCatalogAwareMessage(
  message: string,
  accessToken: string,
  productId?: number | null,
  history?: ChatTurn[] | null,
): Promise<OrchestratedChatResult> {
  if (isReferenceQuery(message)) {
    // A bare follow-up ("comparalas", "¿cuál es mejor?", "ese producto", "los dos")
    // references prior turns. The backend reconstructs those from `history`, so we
    // must NOT search the catalog for the reference word (it only produces noise).
    // Send the raw message + history and let the orchestrator resolve the context.
    const result = await sendChatMessage(message, accessToken, productId, history);
    return { ...result, catalog: emptyCatalog() };
  }
  const catalog = await buildCatalogContext(message, { productId: productId ?? null });
  if (!catalog.detected) {
    const result = await sendChatMessage(message, accessToken, productId, history);
    return { ...result, catalog };
  }
  const prompt = composePrompt(catalog, message);
  const result = await sendChatMessage(prompt, accessToken, productId, history);
  return { ...result, catalog };
}

function emptyCatalog(): CatalogContext {
  return { detected: false, intent: null, query: null, references: [], products: [], statements: [], missing: false };
}

const REFERENCE_PATTERNS = [
  "comparal",
  "comparame",
  "comparar",
  "comparacion",
  "los dos",
  "las dos",
  "ambos",
  "ambas",
  "el primero",
  "el segundo",
  "la primera",
  "la segunda",
  "ese producto",
  "ese",
  "esa",
  "estos",
  "estas",
  "cual es mejor",
  "cual conviene",
  "mejor opcion",
  "y contra",
  "por que",
  "porque",
  "explica",
  "que tiene",
  "cual me conviene",
];

function isReferenceQuery(message: string): boolean {
  const normalized = normalize(message);
  if (!REFERENCE_PATTERNS.some((pattern) => normalized.includes(pattern))) {
    return false;
  }
  // A self-contained query that names its own catalog entity (brand/model/product
  // or a search verb) should keep the normal catalog-aware path; only messages
  // that are purely a reference to prior turns go raw to the backend.
  const namesProduct = PRODUCT_TERMS.concat(BRAND_TERMS, MODEL_TERMS).some((term) => normalized.includes(term));
  const hasSearchVerb = SEARCH_VERBS.some((verb) => normalized.includes(verb));
  return !namesProduct && !hasSearchVerb;
}

export async function buildProductContext(productId: number): Promise<{ intro: string; references: CatalogReference[]; products: ProductRead[] }> {
  const context = await buildCatalogContext("", { productId, forceProductScope: true });
  const product = context.products[0];
  if (!product) {
    return { intro: `No pude cargar el contexto del producto #${productId} desde la API.`, references: [], products: [] };
  }
  const price =
    product.lowest_price !== null && product.lowest_price !== undefined
      ? `desde ${formatCLP(product.lowest_price)}${product.lowest_price_store ? ` en ${product.lowest_price_store}` : ""}`
      : "sin precios cargados";
  const offers = product.offer_count > 0 ? ` · ${product.offer_count} oferta${product.offer_count === 1 ? "" : "s"}` : "";
  return {
    intro: `Contexto cargado del producto #${product.id}: "${product.name}" — ${product.brand ?? "marca no especificada"} · ${product.category} · ${price}${offers}. Podés preguntarme por el precio, dónde está más barato, las ofertas o el historial.`,
    references: context.references,
    products: context.products,
  };
}

export function isProbablyCatalogQuery(message: string, productId?: number | null): boolean {
  const trimmed = message.trim();
  if (!trimmed) return false;
  return detectIntent(trimmed, productId ?? null).intent !== null;
}