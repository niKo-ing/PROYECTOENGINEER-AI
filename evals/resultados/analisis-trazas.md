# Análisis de trazas de la IA

Fuente: `agent_runs` · Ejecuciones: **235**

## Volumen y latencia por flujo

| Flujo | Ejecuciones | Estados | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|---|
| agente | 8 | ok: 7, error: 1 | 5334.6 | 7884.3 | 8066.4 |
| asistente_pc | 227 | ok: 214, error: 1, blocked: 10, fallback: 2 | 2212.2 | 5570.0 | 11046.4 |

## Errores

- `KeyError`: 1
- `rate_limit`: 1

## Respuestas con respaldo (reglas)

- `GoogleRateLimitError`: 2

## Ejecuciones anómalas (> 2 × p95 del flujo)

- dcb0f670eb924e66bf64a73af2c85929 (asistente_pc): 11186.9 ms, umbral 11140.0 ms, herramientas []
- ca2f7ffd101d441d9af33566815be111 (asistente_pc): 12659.2 ms, umbral 11140.0 ms, herramientas []
- d88fb64ab1c04ddc9b9cea056a947f78 (asistente_pc): 21856.3 ms, umbral 11140.0 ms, herramientas []

## Herramientas más usadas

- check_pc_compatibility: 5
- search_pc_parts: 4
- recommend_pc_build: 4
- search_compatibility_guide: 2
- save_pc_build: 1

Ejecuciones con algún error de herramienta: 0 · Replanificaciones: 2

## Precios sin respaldo detectados

- Ninguno.

## Intentos de inyección por hora

- 2026-11-23T01: 11
- 2026-11-23T03: 4

## Auditoría de privacidad

- Sin datos personales en los registros (correos, RUT, teléfonos, tarjetas ni llaves).
