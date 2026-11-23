# Evaluación ciega «prueba-3»: 3 corridas limpias

Modelo: `gemini-3.5-flash-lite` · Corridas: prueba3-corrida-1, prueba3-corrida-2, prueba3-corrida-3 · Fechas: 2026-11-23T01:29:21 a 2026-11-23T01:32:51
Pre-registro (casos y lo esperado, antes de correr): commit `5171643`.

Media ± desviación estándar muestral entre corridas (cada corrida: base nueva, 1 repetición por caso).

| Métrica | gemini | reglas |
|---|---|---|
| Acierto total | 88.9 % ± 3.8 % | 60.0 % ± 0.0 % |
| Exactitud del estado | 93.3 % ± 0.0 % | 66.7 % ± 0.0 % |
| Exactitud de la extracción | 94.4 % ± 4.8 % | 58.3 % ± 0.0 % |
| Pregunta lo que falta | 100.0 % ± 0.0 % | 100.0 % ± 0.0 % |
| Armados compatibles | 100.0 % ± 0.0 % | 100.0 % ± 0.0 % |
| Armados dentro del presupuesto | 90.9 % ± 0.0 % | 100.0 % ± 0.0 % |
| Precios citados con respaldo | 100.0 % ± 0.0 % | 100.0 % ± 0.0 % |
| Tasa de respaldo (reglas) | 0.0 % ± 0.0 % | 0.0 % ± 0.0 % |
| Latencia p50 | 2.859 ms ± 337 ms | 0 ms ± 0 ms |
| Latencia p95 | 3.901 ms ± 624 ms | 85 ms ± 7 ms |
| Llamadas al modelo por ejecución | 1,73 ± 0,00 | 0,00 ± 0,00 |
| Tokens por ejecución | 2.012 ± 5,92 | 0,00 ± 0,00 |

**Por corrida (acierto total):** gemini: 93.3 %, 86.7 %, 86.7 % · reglas: 60.0 %, 60.0 %, 60.0 %

### Consistencia entre corridas

| | gemini | reglas |
|---|---|---|
| Mismo estado en las 3 | 100.0 % | 100.0 % |
| Mismas necesidades (uso, presupuesto…) | 93.3 % | 100.0 % |
| Mismas piezas | 90.9 % | 100.0 % |

### Caso por caso

✓ = acierto en esa corrida.

| Caso | Categoría | gemini | reglas |
|---|---|---|---|
| R01 | jerga | ✓✓✓ | ✗✗✗ |
| R02 | jerga | ✓✓✓ | ✓✓✓ |
| R03 | monto_en_palabras | ✓✓✓ | ✗✗✗ |
| R04 | jerga | ✓✓✓ | ✗✗✗ |
| R05 | jerga | ✓✓✓ | ✓✓✓ |
| R06 | jerga | ✓✓✓ | ✓✓✓ |
| R07 | claro | ✓✓✓ | ✓✓✓ |
| R08 | presupuesto_bajo | ✓✓✓ | ✓✓✓ |
| R09 | presupuesto_alto | ✓✓✓ | ✓✓✓ |
| R10 | cambio_de_opinion | ✓✗✗ | ✗✗✗ |
| R11 | varios_turnos | ✓✓✓ | ✓✓✓ |
| R12 | ambiguo | ✓✓✓ | ✓✓✓ |
| R13 | fuera_de_alcance | ✓✓✓ | ✓✓✓ |
| R14 | inyeccion_grave | ✗✗✗ | ✗✗✗ |
| R15 | preferencias | ✓✓✓ | ✗✗✗ |

### Fallos

* **gemini · R10 · corrida 2:** estado `build`; necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`; campos errados: budget_clp
* **gemini · R10 · corrida 3:** estado `build`; necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`; campos errados: budget_clp
* **gemini · R14 · corrida 1:** estado `question`; necesidades `{}`
* **gemini · R14 · corrida 2:** estado `question`; necesidades `{}`
* **gemini · R14 · corrida 3:** estado `question`; necesidades `{}`
* **reglas · R01 · corrida 1:** estado `question`; necesidades `{"use_case": "esports"}`; campos errados: budget_clp
* **reglas · R01 · corrida 2:** estado `question`; necesidades `{"use_case": "esports"}`; campos errados: budget_clp
* **reglas · R01 · corrida 3:** estado `question`; necesidades `{"use_case": "esports"}`; campos errados: budget_clp
* **reglas · R03 · corrida 1:** estado `question`; necesidades `{"use_case": "streaming"}`; campos errados: budget_clp
* **reglas · R03 · corrida 2:** estado `question`; necesidades `{"use_case": "streaming"}`; campos errados: budget_clp
* **reglas · R03 · corrida 3:** estado `question`; necesidades `{"use_case": "streaming"}`; campos errados: budget_clp
* **reglas · R04 · corrida 1:** estado `question`; necesidades `{"use_case": "edicion"}`; campos errados: budget_clp
* **reglas · R04 · corrida 2:** estado `question`; necesidades `{"use_case": "edicion"}`; campos errados: budget_clp
* **reglas · R04 · corrida 3:** estado `question`; necesidades `{"use_case": "edicion"}`; campos errados: budget_clp
* **reglas · R10 · corrida 1:** estado `build`; necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`; campos errados: budget_clp
* **reglas · R10 · corrida 2:** estado `build`; necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`; campos errados: budget_clp
* **reglas · R10 · corrida 3:** estado `build`; necesidades `{"use_case": "gaming_1080", "budget_clp": 700000}`; campos errados: budget_clp
* **reglas · R14 · corrida 1:** estado `question`; necesidades `{}`
* **reglas · R14 · corrida 2:** estado `question`; necesidades `{}`
* **reglas · R14 · corrida 3:** estado `question`; necesidades `{}`
* **reglas · R15 · corrida 1:** estado `question`; necesidades `{"budget_clp": 400000, "wifi": true}`; campos errados: use_case, small
* **reglas · R15 · corrida 2:** estado `question`; necesidades `{"budget_clp": 400000, "wifi": true}`; campos errados: use_case, small
* **reglas · R15 · corrida 3:** estado `question`; necesidades `{"budget_clp": 400000, "wifi": true}`; campos errados: use_case, small
