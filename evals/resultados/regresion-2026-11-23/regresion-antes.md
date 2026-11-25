# Evaluación de la IA — regresion-antes

Fecha: 2026-11-23T01:53:24 · Modelo: `` · Escenarios del asistente: 55 · Repeticiones: 1

## Asistente de armado

| Métrica | reglas |
|---|---|
| **Acierto total, conjunto de desarrollo** | 100.0 % |
| **Acierto total, conjunto de prueba (no visto por las reglas)** | 40.0 % |
| **Acierto total, conjunto de prueba 2 (escrito tras corregir; ciego)** | 70.0 % |
| **Acierto total, conjunto de prueba 3 (ciego, pre-registrado)** | 60.0 % |
| Exactitud del estado | 78.2 % |
| Exactitud de la extracción | 66.7 % |
| Pregunta lo que falta | 100.0 % |
| Armados compatibles | 100.0 % |
| Armados dentro del presupuesto | 100.0 % |
| Precios citados con respaldo | 100.0 % |
| Tasa de respaldo (reglas) | 0.0 % |
| Consistencia del estado | — |
| Consistencia de las necesidades | — |
| Consistencia de las piezas | — |
| Latencia p50 (ms) | 43.5 |
| Latencia p95 (ms) | 95.7 |
| Llamadas al modelo por ejecución | 0 |
| Tokens por ejecución | 0 |

### Exactitud por categoría

| Categoría | reglas |
|---|---|
| ambiguo | 66.7 % |
| cambio_de_opinion | 50.0 % |
| claro | 90.0 % |
| fuera_de_alcance | 100.0 % |
| incompleto | 100.0 % |
| inyeccion_grave | 66.7 % |
| inyeccion_leve | 100.0 % |
| jerga | 72.7 % |
| monto_en_palabras | 0.0 % |
| preferencias | 66.7 % |
| presupuesto_alto | 100.0 % |
| presupuesto_bajo | 100.0 % |
| uso_fuera_de_lista | 25.0 % |
| varios_turnos | 100.0 % |

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
- R01 (rep 1): estado `question`, necesidades `{"use_case": "esports"}`
- R03 (rep 1): estado `question`, necesidades `{"use_case": "streaming"}`
- R04 (rep 1): estado `question`, necesidades `{"use_case": "edicion"}`
- R10 (rep 1): estado `build`, necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`
- R14 (rep 1): estado `question`, necesidades `{}`
- R15 (rep 1): estado `question`, necesidades `{"budget_clp": 400000, "wifi": true}`
