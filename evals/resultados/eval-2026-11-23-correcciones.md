# Evaluación de la IA — eval-2026-11-23-correcciones

Fecha: 2026-11-23T00:12:30 · Modelo: `gemini-3.5-flash-lite` · Escenarios del asistente: 20 · Repeticiones: 3

## Asistente de armado

| Métrica | gemini | reglas |
|---|---|---|
| **Acierto total, conjunto de prueba (no visto por las reglas)** | 90.0 % | 40.0 % |
| **Acierto total, conjunto de prueba 2 (escrito tras corregir; ciego)** | 90.0 % | 70.0 % |
| Exactitud del estado | 100.0 % | 65.0 % |
| Exactitud de la extracción | 87.5 % | 43.8 % |
| Pregunta lo que falta | 100.0 % | 100.0 % |
| Armados compatibles | 100.0 % | 100.0 % |
| Armados dentro del presupuesto | 93.8 % | 100.0 % |
| Precios citados con respaldo | 100.0 % | 100.0 % |
| Tasa de respaldo (reglas) | 0.0 % | 0.0 % |
| Consistencia del estado | 100.0 % | — |
| Consistencia de las necesidades | 100.0 % | — |
| Consistencia de las piezas | 100.0 % | — |
| Latencia p50 (ms) | 2729.1 | 0.3 |
| Latencia p95 (ms) | 4869.2 | 50.3 |
| Llamadas al modelo por ejecución | 1.75 | 0 |
| Tokens por ejecución | 1881.3 | 0 |

### Exactitud por categoría

| Categoría | gemini | reglas |
|---|---|---|
| ambiguo | 100.0 % | 0.0 % |
| claro | 100.0 % | 75.0 % |
| fuera_de_alcance | 100.0 % | 100.0 % |
| incompleto | 100.0 % | 100.0 % |
| inyeccion_grave | 100.0 % | 100.0 % |
| jerga | 100.0 % | 66.7 % |
| monto_en_palabras | 66.7 % | 0.0 % |
| presupuesto_bajo | 100.0 % | 100.0 % |
| uso_fuera_de_lista | 75.0 % | 25.0 % |
| varios_turnos | 100.0 % | 100.0 % |

### Casos fallidos (gemini)

- P10 (rep 1): estado `build`, necesidades `{"use_case": "gaming_1080", "budget_clp": 2500000}`
- Q08 (rep 1): estado `build`, necesidades `{"use_case": "modelado_ia", "budget_clp": 2000000, "gpu_brand": "NVIDIA"}`
- P10 (rep 2): estado `build`, necesidades `{"use_case": "gaming_1080", "budget_clp": 2500000}`
- Q08 (rep 2): estado `build`, necesidades `{"use_case": "modelado_ia", "budget_clp": 2000000, "gpu_brand": "NVIDIA"}`
- P10 (rep 3): estado `build`, necesidades `{"use_case": "gaming_1080", "budget_clp": 2500000}`
- Q08 (rep 3): estado `build`, necesidades `{"use_case": "modelado_ia", "budget_clp": 2000000, "gpu_brand": "NVIDIA"}`

### Casos fallidos (reglas)

- P01 (rep 1): estado `question`, necesidades `{"use_case": "gaming_1080"}`
- P03 (rep 1): estado `question`, necesidades `{}`
- P04 (rep 1): estado `question`, necesidades `{"budget_clp": 550000}`
- P05 (rep 1): estado `question`, necesidades `{"use_case": "oficina"}`
- P08 (rep 1): estado `question`, necesidades `{"budget_clp": 350000}`
- P10 (rep 1): estado `build`, necesidades `{"use_case": "gaming_1080", "budget_clp": 2500000}`
- Q02 (rep 1): estado `question`, necesidades `{"use_case": "esports"}`
- Q08 (rep 1): estado `build`, necesidades `{"use_case": "modelado_ia", "budget_clp": 2000000}`
- Q09 (rep 1): estado `question`, necesidades `{"budget_clp": 450000}`
