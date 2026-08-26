# Diseño: Alcance del Catálogo Inicial y URL Discovery por Categoría

---

## Estado actual

| Aspecto | Estado |
|---------|--------|
| Model Category | `name` (unique global), `slug`, `parent_id` (self-ref), `enabled`, `sort_order` |
| Jerarquía existente | 8 raíces, ~30 hojas — basada en taxonomy.py (nunca seeded en producción) |
| Product→Category | FK simple (1:1), nullable |
| Connectors → category | Siempre `None` (ni SP Digital ni Paris extraen categoría) |
| On-the-fly creation | Crea categorías root-level sin padre |
| Slug generation | Copy-paste en 3 archivos, sin normalización de tildes |
| API CRUD | Solo GET (list tree, get one). Sin POST/PATCH/DELETE |
| `enabled` field | Existe pero nunca se consulta |
| Detección de categoría | No existe — los productos se ingieren sin categoría |

---

## 1. Categorías — Jerarquía propuesta

### Cambio de diseño: modelo simplificado

El modelo actual (`Category.name` UNIQUE global) impide tener "Accesorios" bajo "Computación" Y bajo "Smartphones". Se requiere:

**Cambiar la constraint UNIQUE de `name` a `(name, parent_id)`** para permitir nombres repetidos en ramas distintas. Esto es lo que dicta la jerarquía real.

### Árbol completo con prioridades

```
Tecnología (raíz, habilitada=false — es agrupador, no categoría productiva)
│
├── P0: Computación
│   ├── P0: Notebooks
│   ├── P0: PCs de escritorio
│   ├── P1: Mini PCs
│   ├── P0: Monitores
│   ├── P0: Procesadores
│   ├── P0: Tarjetas gráficas
│   ├── P0: Placas madre
│   ├── P0: Memoria RAM
│   ├── P0: Almacenamiento SSD
│   ├── P1: Discos duros
│   ├── P1: Fuentes de poder
│   ├── P1: Gabinetes
│   └── P1: Refrigeración PC
│
├── P1: Periféricos
│   ├── P1: Teclados
│   ├── P1: Mouse
│   ├── P1: Audífonos
│   ├── P2: Micrófonos
│   ├── P2: Webcams
│   ├── P2: Mousepads
│   └── P1: Controles / Gamepads
│
├── P0: Gaming
│   ├── P0: Consolas
│   ├── P1: Juegos
│   ├── P1: Controles
│   ├── P2: Accesorios gaming
│   └── P2: Sillas gaming
│
├── P1: Redes
│   ├── P1: Routers
│   ├── P1: Sistemas Wi-Fi Mesh
│   ├── P2: Switches
│   └── P2: Adaptadores de red
│
├── P1: Electrónica
│   ├── P1: Smart TVs
│   ├── P2: Cámaras
│   └── P2: Accesorios electrónicos
│
└── P0: Smartphones
    ├── P0: Celulares
    ├── P1: Tablets
    ├── P2: Smartwatches
    └── P2: Accesorios
```

### Mapa de prioridades

| Prioridad | Categorías | Acción |
|-----------|-----------|--------|
| **P0** | Notebooks, Procesadores, Tarjetas gráficas, Memoria RAM, SSD, Monitores, Placas madre, PCs de escritorio, Celulares, Consolas | Implementar primero, 10-20 URLs/categoría, 2 tiendas |
| **P1** | Mini PCs, Discos duros, Fuentes de poder, Gabinetes, Refrigeración, Teclados, Mouse, Audífonos, Controles, Routers, Wi-Fi Mesh, Juegos, Tablets, Smart TVs | Segunda etapa |
| **P2** | Micrófonos, Webcams, Mousepads, Switches, Adaptadores, Cámaras, Accesorios, Smartwatches, Sillas gaming | Posteriormente |

---

## 2. Reglas de inclusión

Un producto se ingiere SOLO si:

1. **Categoría permitida:** pertenece a una categoría que:
   - existe en el árbol de categorías habilitadas;
   - tiene prioridad P0, P1 o P2;
   - NO es un nodo raíz agrupador (ej: "Tecnología" root).

2. **Identidad mínima:** tiene al menos UNO de:
   - GTIN/EAN
   - MPN + brand (ambos presentes)
   - SKU del fabricante (manufacturer_sku)
   - product_id estable del retailer

3. **Datos básicos:**
   - name no es None ni "Sin nombre"
   - price > 0
   - URL accesible (HTTP 200)
   - currency = "CLP"

4. **No es bundle** (ver sección Variantes/Bundles)

5. **No es servicio** (gift card, garantía extendida, seguro, suscripción)

---

## 3. Reglas de exclusión

### Exclusión por categoría (nunca ingerir)

| Categoría | Razón |
|-----------|-------|
| Ropa, calzado, accesorios de moda | No es tecnología |
| Alimentos, supermercado | No es tecnología |
| Muebles, decoración | No es tecnología |
| Cosméticos, belleza | No es tecnología |
| Artículos de hogar no tecnológicos | Rango amplio, excluir |
| Servicios, gift cards, seguros | No son productos comparables |
| Garantías extendidas | No es producto físico |
| Productos personalizados | No comparable |
| Juguetes (no gaming) | Fuera de alcance |

### Exclusión por señales en el HTML/URL

| Señal | Acción |
|-------|--------|
| URL contiene `/gift-card/`, `/seguro/`, `/garantia/` | Excluir |
| Nombre contiene "gift card", "seguro", "garantía" | Excluir |
| Precio = 0 o None | Excluir |
| Nombre contiene "bundle" + >2 productos listados | Excluir candidato |
| Disponibilidad = OutOfStock por >30 días | Excluir de re-crawl |

---

## 4. Variantes

### Definición

Una variante es el **mismo producto base** con diferente configuración de especificaciones.

### Cómo distinguir variantes vs. productos distintos

**Son variantes** (mismo Product, distinta StoreOffer o mismo Product con specs):
- RTX 5070 / RTX 5070 Ti
- RAM 16GB DDR5 / RAM 32GB DDR5
- SSD 1TB / SSD 2TB
- Notebook i7 16GB / Notebook i7 32GB
- iPhone 16 128GB / iPhone 16 256GB

**NO son variantes** (productos distintos):
- iPhone 16 vs Samsung Galaxy S25
- RTX 5070 vs RX 9070
- Monitor 24" vs Monitor 27" de marcas distintas

### Estrategia de Matching para variantes

El `ProductMatcher` actual ya maneja esto parcialmente:
1. GTIN → match exacto (variante = mismo GTIN)
2. MPN + brand → match exacto (variante = mismo MPN)
3. SKU → match exacto
4. brand + model → match case-insensitive
5. Nombre similar → SequenceMatcher 0.92

**Problema:** El matcher NO distingue variantes de productos distintos cuando el nombre es similar. Un "Notebook Dell Inspiron 15 16GB" y un "Notebook Dell Inspiron 15 32GB" podrían matchear por nombre similar (ratio > 0.92) aunque son variantes distintas.

**Solución propuesta:**
- Agregar campo `variant_group` a Product (nullable, string)
- Cuando se detecta que dos productos son variantes del mismo base, se agrupan
- El matching por nombre similar debe verificar que las specs críticas coincidan antes de aceptar

**NO implementar variant_group todavía** — es suficiente con el matcher actual para P0. Marcar como mejoras futuras.

### Bundles

**Regla inicial:** Excluir bundles cuando:
- El nombre contiene "bundle", "kit", "pack", "conjunto"
- La descripción lista múltiples productos con precios individuales
- El precio es significativamente mayor que la suma de componentes conocidos
- No tiene un identificador claro del bundle como unidad

**Detección:** Buscar patrones en:
- `name`: contiene "bundle", "kit", "pack"
- `description`: lista múltiples items con cantidades
- `price`: anomalía vs. componentes individuales

**NO implementar detección automática de bundles todavía** — marcar como campo `is_bundle: bool | None` en NormalizedOffer para futuro.

---

## 5. Marketplace

### Modelo

```
Store (tienda)
  └── StoreOffer
        ├── seller_name (nullable) — si es marketplace
        └── seller_id (nullable) — identificador estable del seller
```

### Regla actual

El modelo ya soporta `seller_name` en StoreOffer. Falta:
- `seller_id` para identificadores estables
- Lógica para determinar si el seller es "la tienda principal" o un marketplace seller

### Regla de inclusión para marketplace

| Condición | Acción |
|-----------|--------|
| seller_name = nombre de la tienda (ej: "Paris") | Ingresar normalmente |
| seller_name != tienda Y es conocido | Ingresar con seller_name |
| seller_name != tienda Y es desconocido | **NO ingresar** — marcar como `candidate` |
| seller_name = None | Asumir tienda principal |

**NO implementar lógica de detección de marketplace todavía** — por ahora, si `seller_name` está presente y es diferente al store_name, registrar pero no excluir.

---

## 6. Diseño de URL Discovery por Categoría

### Flujo

```
Store (ej: Paris, SP Digital)
  │
  ├── Por cada categoría habilitada (P0 primero)
  │     │
  │     ├── CategoryMapper.map_store_category(store, local_category_name)
  │     │     → Category | None
  │     │
  │     ├── URLDiscovery.discover(store, category)
  │     │     → list[str]  (candidate URLs)
  │     │
  │     ├── CategoryFilter.filter(urls, category)
  │     │     → list[str]  (filtered URLs)
  │     │
  │     └── IngestionQueue.enqueue(urls, category)
  │           → queued for connector
  │
  └── Connector
        → NormalizedOffer (con category assignada)
```

### Componentes nuevos

#### 6.1 CategoryMapper

**Responsabilidad:** Mapear las categorías de una tienda (ej: "Computadores Notebooks" en SP Digital) a nuestro árbol de categorías.

```python
class CategoryMapper:
    """Maps store-specific category names/breadcrumbs to our canonical categories."""

    # Mapping manual inicial por tienda
    MAPPINGS = {
        "www.spdigital.cl": {
            "notebooks": "Notebooks",
            "computadores": "Computación",
            "procesadores": "Procesadores",
            "tarjetas de video": "Tarjetas gráficas",
            # ... etc
        },
        "www.paris.cl": {
            "computacion": "Computación",
            "gaming": "Gaming",
            # ... etc
        }
    }

    def map(self, store_domain: str, store_category: str) -> Category | None:
        """Return canonical Category or None if not mapped."""
```

**Por qué mappings manuales:** Las categorías de cada tienda son inconsistentes. Un mapping automático por nombre tendría baja precisión. Mejor tener un mapping explícito y pequeño que se pueda refinar.

#### 6.2 URLDiscovery

**Responsabilidad:** Descubrir URLs de productos dentro de una categoría de una tienda.

**Estrategia por tienda:**

| Tienda | Estrategia |
|--------|-----------|
| SP Digital (VTEX) | `/{category-slug}/` → parse paginación → extraer links de producto |
| Paris (Next.js) | Buscar en RSC payloads los links de producto por categoría |

**Flujo:**
1. Buscar la página de categoría de la tienda
2. Extraer todos los links de producto
3. Deduplicar
4. Retornar lista de URLs candidatas

#### 6.3 CategoryFilter

**Responsabilidad:** Filtrar URLs que no pertenecen a categorías permitidas.

```python
class CategoryFilter:
    def filter(self, urls: list[str], store_domain: str) -> list[FilterResult]:
        """Return (url, category, confidence) for each URL."""
```

**Señales de categorización (en orden de confianza):**

| Señal | Fuente | Confianza |
|-------|--------|-----------|
| Breadcrumb de categoría mapeada | HTML/RSC | Alta |
| URL path contiene slug de categoría | URL | Media |
| Structured data `@type: Product` + category | JSON-LD | Media |
| Nombre del producto + keyword matching | name | Baja |
| Marca conocida + keyword | brand + name | Baja |

**Regla de confianza mínima:** Si la confianza es < 0.6, marcar como `unknown` y NO ingerir automáticamente.

#### 6.4 EligibilityCheck

**Responsabilidad:** Verificar si un producto es elegible para ingesta.

```python
class EligibilityCheck:
    def check(self, offer: NormalizedOffer) -> EligibilityResult:
        """Return eligible (bool), reason, category, confidence."""
```

**Checks:**
1. ¿Tiene categoría mapeada? (si no → `unknown`, no ingesta)
2. ¿Tiene nombre válido?
3. ¿Tiene precio > 0?
4. ¿Tiene URL?
5. ¿Tiene identificador (GTIN/MPN+brand/SKU/product_id)?
6. ¿Es bundle? (si probablemente → `candidate`, no ingesta automática)
7. ¿Es servicio/gift card? (si → `rejected`)
8. ¿Categoría está en whitelist? (si no → `rejected`)

---

## 7. Cambios de DB necesarios

### 7.1 Category: constraint unique compuesta

**Cambiar** `name` UNIQUE global → `UNIQUE(name, parent_id)`.

Esto permite "Accesorios" bajo "Computación" Y bajo "Smartphones".

```python
class Category(Base):
    __table_args__ = (
        UniqueConstraint("name", "parent_id", name="uq_category_name_parent"),
    )
```

**Nota:** `slug` sigue siendo UNIQUE global (es el identificador URL-safe).

### 7.2 Category: campos nuevos

```python
class Category(Base):
    # ... existente ...
    priority: Mapped[str] = mapped_column(String(4), default="P2")  # "P0", "P1", "P2"
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)  # True = raíz agrupador, no productiva
```

### 7.3 StoreOffer: campos nuevos para marketplace

```python
class StoreOffer(Base):
    # ... existente ...
    seller_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

### 7.4 Resumen de cambios DB

| Tabla | Cambio |
|-------|--------|
| `categories` | UniqueConstraint: `(name, parent_id)` reemplaza `name` unique. +`priority`, +`is_group` |
| `store_offers` | +`seller_id` |
| `ingestion_runs` | Ya creado (run #3) |

---

## 8. Tests

### Tests de CategoryMapper

| Test | Qué valida |
|------|-----------|
| `test_maps_known_category` | Mapping explícito retorna Category correcta |
| `test_returns_none_for_unknown` | Categoría no mapeada retorna None |
| `test_case_insensitive` | Mapping es case-insensitive |
| `test_multiple_stores_different_mappings` | Paris y SP Digital tienen mappings distintos |

### Tests de CategoryFilter

| Test | Qué valida |
|------|-----------|
| `test_filters_excluded_categories` | Ropa, alimentos, etc. son rechazados |
| `test_passes_allowed_categories` | Notebooks, SSD, etc. pasan |
| `test_unknown_category_marked` | Categoría no reconocida → `unknown` |

### Tests de EligibilityCheck

| Test | Qué valida |
|------|-----------|
| `test_eligible_product_with_mpn_brand` | MPN + brand = elegible |
| `test_eligible_product_with_sku` | SKU = elegible |
| `test_rejected_no_name` | Sin nombre → rejected |
| `test_rejected_no_price` | Precio 0 o None → rejected |
| `test_rejected_no_url` | Sin URL → rejected |
| `test_rejected_gift_card` | Nombre contiene "gift card" → rejected |
| `test_rejected_bundle` | Detectado como bundle → candidate |
| `test_rejected_excluded_category` | Categoría en blacklist → rejected |
| `test_unknown_low_confidence` | Confianza < 0.6 → unknown |

### Tests de种子 Categories

| Test | Qué valida |
|------|-----------|
| `test_seed_creates_full_hierarchy` | Todas las categorías del árbol existen |
| `test_seed_is_idempotent` | Ejecutar dos veces no duplica |
| `test_p0_categories_exist` | Todas las P0 existen y están habilitadas |
| `test_leaf_categories_have_parent` | Las hojas tienen parent_id |
| `test_group_categories_not_productive` | Los nodos raíz tienen is_group=True |

---

## 9. Próxima fase (NO implementar ahora)

| Fase | Contenido |
|------|-----------|
| **Fase 1 (actual)** | Categorías, mappings, eligibility, semilla de taxonomy |
| **Fase 2** | URLDiscovery por categoría (SP Digital VTEX pagination, Paris RSC) |
| **Fase 3** | Integración con runners/scheduler — ejecución periódica por categoría |
| **Fase 4** | Métricas detalladas, dashboard, alertas |
| **Fase 5** | Variantes (variant_group), marketplace seller policy |
| **Fase 6** | Kafka, crawlers distribuidos, nuevos connectors |
