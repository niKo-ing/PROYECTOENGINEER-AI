# Store Discovery Report

**Fecha:** 2026-08-25
**Herramienta:** StoreDiscovery (app.ingestion.discovery)
**Metodología:** HTTP GET + HTML parsing + JSON-LD + Embedded JSON + Meta tags + Platform detection

---

## Resumen Ejecutivo

Se analizó 1 URL pública de producto real por tienda usando el Store Discovery Tool recién implementado. Los resultados revelan que las tiendas chilenas varían significativamente en su accesibilidad para extracción de datos estructurados sin JavaScript.

| Tienda | URL | Plataforma | JSON-LD | Precio | Stock | SKU | GTIN | MPN | Método | Dificultad |
|--------|-----|------------|---------|--------|-------|-----|------|-----|--------|------------|
| SP Digital | spdigital.cl | VTEX (0.30) | No | **Sí** | **Sí** | No* | No | **Sí** | Meta tags | **Baja** |
| Paris | paris.cl | Next.js (0.30) | RSC† | Texto† | No | Texto† | No | No | RSC payload | Media |
| MyShop | myshop.cl | Desconocido | No | No | No | No | No | No | Meta OG | Alta |
| PC Factory | pcfactory.cl | Desconocido (SPA) | No | No | No | No | No | No | Shell HTML | Muy Alta |
| Falabella | falabella.com | Cloudflare | N/A | N/A | N/A | N/A | N/A | N/A | Bloqueado | No viable |

† = Detectado en inspección manual, no por el Discovery Tool estándar
\* = Detectado como `product-id` en meta tags, no como `sku`

---

## Análisis Detallado por Tienda

### 1. SP Digital

**URL:** `https://www.spdigital.cl/consola-playstation-5-slim-edicion-digital-sony-color-blanco/`

| Campo | Resultado | Tipo de dato |
|-------|-----------|--------------|
| HTTP Status | **200** | Observado |
| Final URL | Igual a original (sin redirect) | Observado |
| Content-Type | `text/html` | Observado |
| Tamaño respuesta | ~HTML estándar | Observado |
| Plataforma | **VTEX** (confidence: 0.30) | Inferido (señales: "vtex" en HTML) |
| JSON-LD | **No encontrado** | Observado |
| Product | **No** | Observado |
| Offer | **No** | Observado |
| Nombre | **Sí** — "Consola PlayStation 5 Slim Edición Digital Sony, Color Blanco" | Observado (meta `og:title`) |
| Precio | **Sí** — **699990** | Observado (meta `product:price:amount`) |
| Moneda | **Sí** — **CLP** | Observado (meta `product:price:currency`) |
| Disponibilidad | **Sí** — **"in stock"** | Observado (meta `product:availability`) |
| SKU | **No encontrado** directamente. `product-id: NA0000081556` y `retailer_item_id: 79154` disponibles | Observado |
| GTIN/EAN | **No encontrado** | No encontrado |
| MPN | **Sí** — **1000039670** | Observado (meta `product:mfr_part_no`) |
| Marca | **Sí** — **SONY** | Observado (meta `product:brand`) |
| Imagen | **Sí** — URL completa | Observado (meta `og:image`) |
| URL producto | **Sí** | Observado (meta `og:url`) |
| Embedded JSON | **No** | Observado |
| Meta data | **Sí** — 14 meta tags relevantes | Observado |
| Warnings | Ninguno | — |
| Errors | Ninguno | — |

**Fuentes de datos encontradas:** `meta-tags`

**Observaciones:**
- VTEX provee meta tags ricos en el HTML estándar, sin necesidad de JavaScript.
- El precio, moneda, disponibilidad, marca y MPN están todos en meta tags `<product:*>`.
- No hay JSON-LD, pero los meta tags VTEX son equivalentes en información.
- El campo `product-id` (NA0000081556) podría servir como `external_id`.
- **Es la tienda más accesible para ingesta sin JavaScript.**

---

### 2. Paris

**URL:** `https://www.paris.cl/607430.html` (redirige a `/camiseta-de-futbol-chile-2024-local-607430.html`)

| Campo | Resultado | Tipo de dato |
|-------|-----------|--------------|
| HTTP Status | **200** | Observado |
| Final URL | Redirect a URL con slug SEO | Observado |
| Content-Type | `text/html; charset=utf-8` | Observado |
| Tamaño respuesta | **2.2 MB** (HTML grande) | Observado |
| Plataforma | **Next.js** (confidence: 0.30) | Inferido (señales: `/_next/static/chunks`) |
| JSON-LD | **No detectado** por herramienta estándar | Observado |
| Product | **No detectado** | Observado |
| Offer | **No detectado** | Observado |
| Nombre | **Sí** — "Camiseta de Fútbol Chile 2024 Local Adidas" | Observado (meta `og:title`) |
| Precio | **Sí** — `$23.990` y `$59.990` en texto del body | Inferido (regex en body text) |
| Moneda | **No detectado** por herramienta | No encontrado |
| Disponibilidad | **No** | No encontrado |
| SKU | **Sí** — `607430002` en body text | Inferido (regex `SKU: 607430002`) |
| GTIN/EAN | **No** | No encontrado |
| MPN | **No** | No encontrado |
| Marca | **No detectada** por herramienta | No encontrado |
| Imagen | **Sí** — URL completa (Cencosud CDN) | Observado (meta `og:image`) |
| URL producto | **Sí** | Observado (meta `og:url`) |
| Embedded JSON | **No detectado** | Observado |
| Meta data | **Sí** — 14 meta tags | Observado |
| Warnings | Ninguno | — |
| Errors | Ninguno | — |

**Fuentes de datos encontradas:** `meta-tags`

**Inspección manual adicional (fuera del Discovery Tool estándar):**
- El HTML contiene **284 scripts RSC** (React Server Components) de Next.js.
- Dentro de los RSC payloads se encontró:
  - **JSON-LD Product completo** en formato `self.__next_f.push([1,"..."])` (~50KB)
  - Datos del producto: name, brand, sku, offers.price, offers.priceCurrency, offers.availability
  - La data del producto está serializada como string dentro de `self.__next_f.push()`
- **No está en `<script type="application/ld+json">`** estándar, por eso el Discovery Tool no lo detecta.
- El HTML tiene 365 tags `<script>`, la mayoría chunks de Next.js.

**Dato observado:** og:title, og:image, og:url
**Dato inferido:** precio del body text, SKU del body text
**Dato que requiere JavaScript:** JSON-LD completo (en RSC payload), disponibilidad, marca exacta
**Dato no encontrado:** GTIN, MPN, moneda explícita

---

### 3. MyShop

**URL:** `https://www.myshop.cl/producto/vector-16-hx-ai-a2xwhg-661cl-p43107`

| Campo | Resultado | Tipo de dato |
|-------|-----------|--------------|
| HTTP Status | **200** | Observado |
| Final URL | Igual a original | Observado |
| Content-Type | `text/html; charset=utf-8` | Observado |
| Tamaño respuesta | **4.7 MB** (HTML muy grande) | Observado |
| Plataforma | **Desconocida** | — |
| JSON-LD | **No** | Observado |
| Product | **No** | Observado |
| Offer | **No** | Observado |
| Nombre | **Sí** — "Notebook Gamer - MSI Vector 16 HX AI A2XWHG..." (en `og:title`) | Observado |
| Precio | **No** | No encontrado |
| Moneda | **No** | No encontrado |
| Disponibilidad | **No** | No encontrado |
| SKU | **No** (pero visible en búsquedas: "SKU 43107") | No encontrado en HTML analizado |
| GTIN/EAN | **No** | No encontrado |
| MPN | **No** | No encontrado |
| Marca | **No detectada** | No encontrado |
| Imagen | **Sí** — URL completa (static.myshop.cl) | Observado (meta `og:image`) |
| URL producto | **Sí** | Observado (meta `og:url`) |
| Embedded JSON | **No** | Observado |
| Meta data | **Sí** — 5 meta tags básicos | Observado |
| Warnings | Ninguno | — |
| Errors | Ninguno | — |

**Fuentes de datos encontradas:** `meta-tags`

**Observaciones:**
- El HTML tiene 4.7 MB pero el contenido visible es mínimo (~5300 chars).
- Los meta tags son genéricos (`og:type: website`), no específicos de producto.
- `og:title` contiene el nombre del producto, pero `og:description` dice "Busca mas productos en https://www.myshop.cl" (genérico).
- La data del producto (SKU, precio, marca, especificaciones) se carga vía JavaScript/API.
- **Es un SPA con Server-Side Rendering limitado.**

---

### 4. PC Factory

**URL:** `https://www.pcfactory.cl/producto/54239-tplink-router-mesh-tplink-deco-x20-2-pack-ax1800-next-gen-dual-band`

| Campo | Resultado | Tipo de dato |
|-------|-----------|--------------|
| HTTP Status | **200** | Observado |
| Final URL | Igual a original | Observado |
| Content-Type | `text/html; charset=utf-8` | Observado |
| Tamaño respuesta | **222 KB** | Observado |
| Plataforma | **Desconocida** (SPA custom) | — |
| JSON-LD | **No** | Observado |
| Product | **No** | Observado |
| Offer | **No** | Observado |
| Nombre | **No** — Title es "icono-automóvil-gps_y_outdoor" (placeholder) | Observado |
| Precio | **No** | No encontrado |
| Moneda | **No** | No encontrado |
| Disponibilidad | **No** | No encontrado |
| SKU | **No** | No encontrado |
| GTIN/EAN | **No** | No encontrado |
| MPN | **No** | No encontrado |
| Marca | **No** | No encontrado |
| Imagen | **No** | No encontrado |
| URL producto | **No** | No encontrado |
| Embedded JSON | **No** | Observado |
| Meta data | **Sí** — solo viewport y apple-mobile-web-app-capable | Observado |
| Warnings | Ninguno | — |
| Errors | Ninguno | — |

**Fuentes de datos encontradas:** `meta-tags` (mínimo)

**Observaciones:**
- El HTML es un **shell de aplicación** completamente vacío.
- El título "icono-automóvil-gps_y_outdoor" es un placeholder/ícono, no un título de producto.
- Todo el contenido del producto se renderiza con JavaScript.
- No hay ningún dato de producto en el HTML estándar.
- **Es la SPA más pura de las 5 tiendas — 100% client-side rendering.**
- El body tiene solo ~1336 chars de texto visible (navegación genérica).

---

### 5. Falabella

**URL:** `https://www.falabella.com/falabella-cl/product/145445120/Apple-iPhone-15-128gb-5G-Rosa/145445121`

| Campo | Resultado | Tipo de dato |
|-------|-----------|--------------|
| HTTP Status | **403** | Observado |
| Final URL | Igual a original | Observado |
| Content-Type | `text/html; charset=UTF-8` | Observado |
| Tamaño respuesta | N/A (respuesta de bloqueo) | Observado |
| Plataforma | **No detectada** (bloqueado) | — |
| JSON-LD | **N/A** | — |
| Product | **N/A** | — |
| Offer | **N/A** | — |
| Nombre | **No** | — |
| Precio | **No** | — |
| Todos los campos | **No disponibles** | — |
| Meta data | **Sí** — robots: noindex, nofollow; title: "Cloudflare" | Observado |
| Warnings | Ninguno | — |
| Errors | **HTTP 403** | Observado |

**Observaciones:**
- La tienda está protegida por **Cloudflare WAF/Bot Protection**.
- La respuesta HTTP 403 indica que el request fue bloqueado antes de llegar a la aplicación.
- El HTML retornado es la página de challenge de Cloudflare, no el producto.
- **No es viable acceder con HTTP GET simple.**
- Se necesitaría: bypass de Cloudflare (no implementado), API oficial, o browser rendering.

---

## Ranking: Más fácil a más difícil

| Rank | Tienda | Dificultad | Razón |
|------|--------|------------|-------|
| 1 | **SP Digital** | **Baja** | VTEX provee meta tags ricos con precio, moneda, marca, MPN, disponibilidad en HTML estándar. Sin JSON-LD pero equivalente funcional. |
| 2 | **Paris** | **Media** | Next.js con RSC. JSON-LD y datos de producto existen en el HTML pero empaquetados en streaming format RSC. Requiere parser custom para extraer `self.__next_f.push()` payloads. |
| 3 | **MyShop** | **Alta** | SPA con SSR limitado. Solo og:title, og:image. Precio, stock, SKU, marca se cargan vía JS. HTML de 4.7MB con poco contenido. |
| 4 | **PC Factory** | **Muy Alta** | SPA pura. Shell HTML completamente vacío. Título placeholder. 100% de datos en JavaScript. |
| 5 | **Falabella** | **No viable** | Cloudflare WAF bloquea HTTP GET. 403 forbidden. No hay acceso al contenido sin browser rendering o bypass. |

---

## Tienda Recomendada para Implementar Primero

### **SP Digital**

### Razón de la Elección

1. **Datos accesibles sin JavaScript:** VTEX entrega precio, moneda, marca, MPN, disponibilidad e imagen en meta tags HTML estándar.
2. **Sin protección anti-bot agresiva:** HTTP 200 con contenido completo en la primera respuesta.
3. **Plataforma conocida:** VTEX es una plataforma e-commerce estándar con documentación pública.
4. **Datos completos observables:**
   - Precio: `product:price:amount` = 699990
   - Moneda: `product:price:currency` = CLP
   - Marca: `product:brand` = SONY
   - MPN: `product:mfr_part_no` = 1000039670
   - Disponibilidad: `product:availability` = in stock
   - Imagen: URL completa
   - External ID: `product-id` = NA0000081556
5. **Baja dificultad de implementación:** Un `StoreConnector` para VTEX puede extraer datos directamente de meta tags sin parsing complejo.

### Qué Datos Podemos Ingerir Actualmente (SP Digital)

| Dato | Fuente | Confianza |
|------|--------|-----------|
| Nombre del producto | `og:title` | Alta |
| Precio | `product:price:amount` | Alta |
| Moneda | `product:price:currency` | Alta |
| Marca | `product:brand` | Alta |
| MPN | `product:mfr_part_no` | Alta |
| Disponibilidad | `product:availability` | Alta |
| Imagen | `og:image` | Alta |
| External ID | `product-id` | Alta |
| URL del producto | `og:url` | Alta |
| Condición | `product:condition` | Alta |

### Qué Datos Nos Faltan (SP Digital)

| Dato | Estado | Notas |
|------|--------|-------|
| SKU | Parcial | `retailer_item_id: 79154` disponible, pero no como "SKU" estándar |
| GTIN/EAN | No encontrado | No está en meta tags. Podría estar en JSON-LD (no detectado) o en el body renderizado por JS |
| Categoría | No encontrada | No en meta tags. Podría estar en el body o en API VTEX |
| Precio anterior / descuento | No encontrado | No en meta tags |
| Descripción | No encontrada | No en meta tags analizados |
| Seller | No encontrado | VTEX puede tener múltiples sellers |

---

## Conclusión

El Store Discovery Tool demuestra que **SP Digital (VTEX) es la única tienda actualmente viable para ingesta sin JavaScript**. Paris tiene datos potenciales en RSC payloads pero requiere un parser adicional. Las demás tiendas requieren JavaScript rendering o están bloqueadas.

**Próximo paso recomendado:** Implementar un `StoreConnector` específico para VTEX/SP Digital que extraiga datos de meta tags, como primera iteración del pipeline de ingesta.
