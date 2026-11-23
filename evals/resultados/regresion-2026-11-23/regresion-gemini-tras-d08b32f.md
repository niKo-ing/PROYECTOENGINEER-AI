# Evaluación de la IA — regresion-gemini-tras-d08b32f

Fecha: 2026-11-23T09:23:28 · Modelo: `gemini-3.5-flash-lite` · Escenarios del asistente: 35 · Repeticiones: 1

## Asistente de armado

| Métrica | gemini |
|---|---|
| **Acierto total, conjunto de prueba (no visto por las reglas)** | 90.0 % |
| **Acierto total, conjunto de prueba 2 (escrito tras corregir; ciego)** | 100.0 % |
| **Acierto total, conjunto de prueba 3 (ciego, pre-registrado)** | 100.0 % |
| Exactitud del estado | 97.1 % |
| Exactitud de la extracción | 96.4 % |
| Pregunta lo que falta | 100.0 % |
| Detección de inyecciones (casos que la fijan) | — |
| Armados compatibles | 100.0 % |
| Armados dentro del presupuesto | 92.3 % |
| Precios citados con respaldo | 100.0 % |
| Tasa de respaldo (reglas) | 2.9 % |
| Consistencia del estado | — |
| Consistencia de las necesidades | — |
| Consistencia de las piezas | — |
| Latencia p50 (ms) | 3371.9 |
| Latencia p95 (ms) | 4158.5 |
| Llamadas al modelo por ejecución | 1.69 |
| Tokens por ejecución | 1961.3 |

### Exactitud por categoría

| Categoría | gemini |
|---|---|
| ambiguo | 100.0 % |
| cambio_de_opinion | 100.0 % |
| claro | 100.0 % |
| fuera_de_alcance | 100.0 % |
| incompleto | 100.0 % |
| inyeccion_grave | 100.0 % |
| jerga | 100.0 % |
| monto_en_palabras | 100.0 % |
| preferencias | 100.0 % |
| presupuesto_alto | 100.0 % |
| presupuesto_bajo | 100.0 % |
| uso_fuera_de_lista | 75.0 % |
| varios_turnos | 100.0 % |

### Casos fallidos (gemini)

- P08 (rep 1): estado `question`, necesidades `{"budget_clp": 350000}`
