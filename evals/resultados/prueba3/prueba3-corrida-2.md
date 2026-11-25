# Evaluación de la IA — prueba3-corrida-2

Fecha: 2026-11-23T01:31:03 · Modelo: `gemini-3.5-flash-lite` · Escenarios del asistente: 15 · Repeticiones: 1

## Asistente de armado

| Métrica | gemini | reglas |
|---|---|---|
| **Acierto total, conjunto de prueba 3 (ciego, pre-registrado)** | 86.7 % | 60.0 % |
| Exactitud del estado | 93.3 % | 66.7 % |
| Exactitud de la extracción | 91.7 % | 58.3 % |
| Pregunta lo que falta | 100.0 % | 100.0 % |
| Armados compatibles | 100.0 % | 100.0 % |
| Armados dentro del presupuesto | 90.9 % | 100.0 % |
| Precios citados con respaldo | 100.0 % | 100.0 % |
| Tasa de respaldo (reglas) | 0.0 % | 0.0 % |
| Consistencia del estado | — | — |
| Consistencia de las necesidades | — | — |
| Consistencia de las piezas | — | — |
| Latencia p50 (ms) | 2892.9 | 0.4 |
| Latencia p95 (ms) | 4547.4 | 93.4 |
| Llamadas al modelo por ejecución | 1.73 | 0 |
| Tokens por ejecución | 2019.3 | 0 |

### Exactitud por categoría

| Categoría | gemini | reglas |
|---|---|---|
| ambiguo | 100.0 % | 100.0 % |
| cambio_de_opinion | 0.0 % | 0.0 % |
| claro | 100.0 % | 100.0 % |
| fuera_de_alcance | 100.0 % | 100.0 % |
| inyeccion_grave | 0.0 % | 0.0 % |
| jerga | 100.0 % | 60.0 % |
| monto_en_palabras | 100.0 % | 0.0 % |
| preferencias | 100.0 % | 0.0 % |
| presupuesto_alto | 100.0 % | 100.0 % |
| presupuesto_bajo | 100.0 % | 100.0 % |
| varios_turnos | 100.0 % | 100.0 % |

### Casos fallidos (gemini)

- R10 (rep 1): estado `build`, necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`
- R14 (rep 1): estado `question`, necesidades `{}`

### Casos fallidos (reglas)

- R01 (rep 1): estado `question`, necesidades `{"use_case": "esports"}`
- R03 (rep 1): estado `question`, necesidades `{"use_case": "streaming"}`
- R04 (rep 1): estado `question`, necesidades `{"use_case": "edicion"}`
- R10 (rep 1): estado `build`, necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`
- R14 (rep 1): estado `question`, necesidades `{}`
- R15 (rep 1): estado `question`, necesidades `{"budget_clp": 400000, "wifi": true}`
