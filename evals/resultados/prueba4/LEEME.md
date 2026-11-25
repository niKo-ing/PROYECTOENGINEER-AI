# Corridas crudas de `prueba-4`

Pre-registro: `evals/preregistro-prueba-4.md` (commit `735202b`). Resultado agregado:
`evals/resultados/eval-2026-11-23-prueba4.md`.

| Archivo | Inicio (23-11, Chile) | ¿Vale? | Motivo |
|---|---|---|---|
| `prueba4-corrida-1.json` / `.md` | 01:53 | Sí | Sin errores del modelo ni respaldos |
| `prueba4-corrida-2.json` / `.md` | 01:55 | Sí | Sin errores del modelo ni respaldos |
| `invalida-intento-1-prueba4-corrida-3.json` | 01:56 | No | 3 filas con `GoogleRateLimitError` (cuota diaria agotada); 2 en respaldo |
| (intento 2, sin archivo) | madrugada | No | Se detuvo a mano: todas las llamadas devolvían 429 por la cuota diaria |
| `invalida-intento-3-prueba4-corrida-3-repetida.json` | 09:11 | No | S01 con `GoogleAPIError` (respaldo) y S03 con `ReadTimeout` |
| `prueba4-corrida-3-intento-4.json` / `.md` | 09:20 | Sí | Sin errores del modelo ni respaldos |

La regla del pre-registro: una corrida vale si ninguna fila de Gemini terminó con error del modelo ni en respaldo por
reglas; si no vale, se repite completa y se informa. Las tres fallas fueron de la API de Google (cuota y tiempo de
espera), no del comportamiento del modelo. Los casos, lo esperado, los umbrales y el código no se tocaron entre
intentos. Cada corrida usó una base nueva y 1 repetición por caso.
