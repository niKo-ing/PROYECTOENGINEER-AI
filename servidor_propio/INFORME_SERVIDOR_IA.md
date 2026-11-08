# TodoBarato AI en servidor propio: hardware y costos

Pregunta: **¿qué computador o servidor físico ("tarro") necesitamos para correr nosotros mismos la IA y todas las páginas de TodoBarato AI, cuánto cuesta comprarlo y cuánto cuesta mantenerlo funcionando?**

En la EP2 la app corría en AWS (USD 120,44/mes) y la IA se pagaba por uso a Gemini (≈ USD 55/mes). Este informe estudia la alternativa: **todo en casa, con un modelo de IA abierto en una GPU propia**.

Precios consultados el 08-11-2026 · dólar $975 · luz $280/kWh · cálculo reproducible en `costos_servidor_propio.py`.

---

## 1. Qué tiene que correr el servidor

### Páginas de la app (frontend Next.js)

| Página | Ruta | Qué usa en el servidor | Usa IA |
|---|---|---|---|
| Inicio | `/` | API de productos y categorías | No |
| Búsqueda | `/search` | API + base de datos (filtros, sinónimos) | No |
| Categoría | `/category/[slug]` | API + base de datos (facetas, orden) | No |
| Producto | `/product/[id]` | Ofertas por tienda, historial de precios, galería, especificaciones | No |
| Comparar | `/compare` | Especificaciones de varios productos | No |
| Chat IA | `/chat` | Orquestador + RAG + **LLM** (hasta 3 llamadas por consulta) | **Sí** |
| Agente | `/agente` | Agente LangGraph: plan, herramientas, alertas, memoria + **LLM** | **Sí** |
| Login / Registro | `/login`, `/register` | Supabase Auth | No |
| Admin | `/admin` | Ingestas, revisión de especificaciones | Parcial |

### Servicios de fondo

| Servicio | Hoy (EP2) | En servidor propio |
|---|---|---|
| Frontend Next.js | EC2 | Contenedor Docker |
| Backend FastAPI | 2 × EC2 t3.small | Contenedor Docker (4 workers) |
| Base de datos PostgreSQL | RDS | Contenedor PostgreSQL en SSD NVMe en RAID 1 |
| Worker de ingesta (scraping de Paris y SP Digital) | EC2 t3.small | Contenedor programado (cron) |
| **Modelo de IA (LLM)** | **Gemini por API** | **vLLM u Ollama con un modelo abierto en la GPU** |
| Embeddings del RAG | Locales (256 dimensiones, livianos) | Iguales: no necesitan GPU |
| Usuarios (login) | Supabase | Se mantiene Supabase (plan gratuito) |
| HTTPS y dominio | CloudFront | Cloudflare (gratis) + dominio .cl |

El código está casi listo: `LLM_PROVIDER` permite cambiar de proveedor, y vLLM y Ollama exponen una API compatible con OpenAI. Solo falta que el adaptador OpenAI (`app/ai/providers/openai_provider.py`) y el agente (`app/agent/llm.py`) acepten una dirección propia (`OPENAI_BASE_URL`); hoy siempre apuntan a OpenAI o a Gemini.

## 2. Cuánta IA hay que aguantar

Usamos los mismos supuestos de carga que la EP2: 1.500 consultas de chat/agente al día, 3 llamadas al LLM por consulta, 2.500 tokens de entrada y 400 de salida, y una hora pico 6 veces mayor que el promedio.

| Indicador en la hora pico | Valor |
|---|---|
| Llamadas al LLM | 0,31 por segundo |
| Tokens de entrada a procesar | ~780 por segundo |
| Tokens de salida a generar | ~125 por segundo |

Con vLLM, **una sola GPU de 24-32 GB supera los 1.000 tokens/s** en un modelo de 8B. La carga es pequeña, así que **no hace falta un servidor de varias GPU**. Modelos que caben:

| GPU | Modelos abiertos sugeridos |
|---|---|
| 32 GB (RTX 5090) | Llama 3.1 8B o Qwen 2.5 7B a precisión completa; Qwen3-30B-A3B o Gemma 3 27B cuantizados a 4 bits |
| 96 GB (RTX PRO 6000) | Modelos de 30B a 70B cuantizados, con mucho espacio para atender varios usuarios a la vez |

No se entrena ningún modelo, solo se usa (inferencia). Por eso no se necesitan GPU de entrenamiento como la H100.

## 3. Opciones de hardware y su costo de compra

### Opción A: workstation "tarro" con RTX 5090 (recomendada)

| Componente | CLP |
|---|---|
| PC workstation Intel Core Ultra 9 285K, 192 GB RAM, RTX 5090 32 GB (Paris.cl, con 12 % de descuento) | 9.617.520 |
| 2 SSD NVMe de 2 TB para RAID 1 (base de datos y respaldos) | 400.000 |
| UPS online de 1,5 kVA (cortes de luz) | 550.000 |
| **Inversión inicial** | **10.567.520** |

Como referencia, la RTX 5090 sola cuesta desde $6.399.500 en Solotodo, más de la mitad del total.

### Opción B: servidor de rack "industrial" con RTX PRO 6000 de 96 GB

| Componente | CLP |
|---|---|
| Dell PowerEdge R760xa base (2 Xeon, 128 GB, 2 SSD), ~USD 12.000 | 11.700.000 |
| GPU NVIDIA RTX PRO 6000 Blackwell 96 GB, ~USD 10.000 | 9.750.000 |
| Internación: flete + IVA del 19 % (~25 %) | 5.362.500 |
| Rack 24U + PDU | 900.000 |
| UPS online de 3 kVA para rack | 1.600.000 |
| **Inversión inicial** | **29.312.500** |

La opción B tiene piezas redundantes (dos fuentes, iDRAC para administrarlo a distancia, garantía empresarial) y aguanta mucho más crecimiento. Pero es ruidosa, necesita aire acondicionado y, con la carga actual, está sobredimensionada.

## 4. Costo mensual para mantenerlo funcionando

| Ítem | A: tarro RTX 5090 | B: rack RTX PRO 6000 |
|---|---|---|
| Depreciación del hardware (se paga en 3 años) | 293.542 | 814.236 |
| Electricidad 24×7 (A: 300 W promedio; B: 550 W + 50 % de aire acondicionado) | 61.320 | 168.630 |
| Internet fibra para empresas con IP fija (Entel Fibra Plus, ~1,92 UF + IVA) | 92.000 | 92.000 |
| Mantención de un técnico (parches, respaldos, monitoreo; $15.000/h) | 120.000 (8 h) | 180.000 (12 h) |
| Reserva para repuestos (5 % del hardware al año) | 44.031 | 122.135 |
| Dominio .cl + respaldo externo de la base | 6.000 | 6.000 |
| **Total mensual** | **$616.894 (~USD 633)** | **$1.383.002 (~USD 1.418)** |
| **Total a 3 años** | **$22.208.168** | **$49.788.055** |

## 5. Comparación con la nube de la EP2

| Alternativa | CLP/mes | Frente a la EP2 |
|---|---|---|
| EP2: AWS + Gemini por API | 171.395 | 1× |
| GPU arrendada en AWS (g5.xlarge 24×7, solo la GPU) | 716.020 | 4,2× |
| **A: tarro propio con RTX 5090 (incluye todas las páginas)** | **616.894** | **3,6×** |
| B: servidor de rack propio | 1.383.002 | 8,1× |

**Punto de equilibrio:** la opción A sale más barata que AWS + Gemini cuando la app pasa de **~13.900 consultas de IA al día**, unas 9 veces la carga actual. Gemini cobra por cada consulta y el servidor propio cuesta lo mismo con 100 o con 13.000 consultas.

## 6. Conclusión

- **Con la carga actual conviene seguir en la nube.** Es la misma conclusión de la EP2: la API es unas 3,6 veces más barata que tener un servidor propio.
- **Si se exige servidor propio** (por privacidad de los datos, para no depender de Google o porque se espera mucho crecimiento), la mejor opción es la **A: un tarro con RTX 5090 de 32 GB**. Corre el modelo de IA, la base de datos, la API, el scraping y todas las páginas en una sola máquina, por **~$10,6 millones de inversión y ~$617 mil al mes**.
- El servidor de rack (B) solo se justifica si se esperan más de ~10 veces los usuarios actuales o si se necesita garantía y redundancia de nivel empresa.
- **Riesgo principal de A:** es una sola máquina. Si falla, la página se cae. Para reducir el riesgo se pueden respaldar la base y las imágenes Docker en la nube todos los días, y usar Gemini como respaldo si la GPU falla (basta con cambiar `LLM_PROVIDER`).

## Fuentes

- PC workstation con RTX 5090 y 192 GB: [Paris.cl](https://www.paris.cl/pc-workstation-intel-ultra-9-285k-192gb-rtx-5090-32gb-or-pcw097-MKFLWFNVU8.html)
- RTX 5090 sola: [Solotodo](https://www.solotodo.cl/products/265691-msi-geforce-rtx-5090-32g-gaming-trio-oc-g5090-32gtc)
- RTX PRO 6000 Blackwell: [Tom's Hardware](https://www.tomshardware.com/pc-components/gpus/nvidia-rtx-pro-6000-blackwell-gpu-is-listed-for-usd8-565-at-us-retailer-26-percent-more-expensive-than-the-last-gen-rtx-6000-ada), [TweakTown](https://www.tweaktown.com/news/113098/nvidias-rtx-pro-6000-blackwell-gpu-price-almost-doubles-reaching-dollars16000/index.html)
- Dell PowerEdge R760xa: [Dell](https://www.dell.com/en-us/shop/cty/pdp/spd/poweredge-r760xa/pe_r760xa_16902_vi_vp), [Servermall](https://servermall.com/en-us/config/dell-r760xa-8sff-new/)
- Tarifa eléctrica BT1 2026: [EEPA](https://eepa.cl/pdfs/Publicación-Tarifas-Suministro-08-2026_5T-24T.pdf), [Grupo Saesa](https://www.gruposaesa.cl/distribuidoras/descargar-archivos/7352/)
- Dólar en noviembre de 2026: [Emol](https://www.emol.com/noticias/Economia/2026/11/06/1216310/dolar-sube-ipc-wall-street.html)
- Fibra para empresas con IP fija: [Entel Empresas](https://empresas.entel.cl/articulos/fibra-plus-vs-fibra-estandar-cual-conviene-en-una-empresa)
- Supuestos de carga y costos en la nube: `EP2_ITY1102/infra/costos.py` y `EP2_ITY1102/infra/calculadora/README.md` del repositorio

> Los precios de las GPU subieron mucho en 2026 y cambian casi todas las semanas. Antes de entregar, conviene volver a revisar los dos o tres precios más grandes.
