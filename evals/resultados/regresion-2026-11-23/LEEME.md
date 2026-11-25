# Regresión de las correcciones de `d08b32f` (R14 y R10)

Lo pide el pre-registro de `prueba-4` (`evals/preregistro-prueba-4.md`, sección «Regresión»). No es evidencia nueva.

* `regresion-antes.*` y `regresion-despues.*`: banco completo en modo solo reglas (determinista) con el código antes
  (`e489ee9`) y después de las correcciones. Ningún conjunto baja; solo cambia R14 (de pregunta a bloqueado), así que
  `prueba-3` sube de 60 % a 66,7 %.
* `regresion-gemini-tras-d08b32f.*`: 1 corrida de Gemini sobre `prueba`, `prueba-2` y `prueba-3` (23-11, 09:2x).
  `prueba` 90 % (P08 cayó al respaldo: una salida de Gemini no se pudo leer), `prueba-2` 100 %, `prueba-3` 100 %.
  `prueba-3` está contaminado (las correcciones se hicieron mirando sus fallos): no cuenta como medición.
