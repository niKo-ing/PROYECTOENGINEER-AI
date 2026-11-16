# Preguntas probables de la defensa (EP3) y respuestas

> Regla: responder con **un dato medido** y reconocer el límite. Las cifras salen de `modelo/metrics.json`, `pruebas/resultados/` y `evidencia/`.

## Modelo (IE1, IE3)
**1. ¿Por qué un Random Forest y no una red neuronal o un LLM?**
Son datos tabulares y pocos (554 pares): un bosque rinde bien sin tanto dato, entrena en segundos, no necesita GPU y es interpretable (importancia de características y razones por decisión). Un LLM resuelve el caso pero con latencia y costo por llamada mucho mayores; el modelo propio atiende la zona gris que el emparejador determinista deja «ambigua».

**2. ¿Qué tan confiables son sus métricas?**
Honestamente: F1 0,908 contra 0,832 de la línea base, en pares **sintéticos de una sola tienda** y partición por producto. La primera versión dio F1 = 1,00 y lo tratamos como señal de examen circular: agregamos ruido (erratas, datos faltantes, abreviaturas) hasta obtener un valor creíble. La validación definitiva necesita pares reales entre tiendas; por eso guardamos cada decisión en `ai_match_decisions`.

**3. ¿Por qué el umbral 0,70?**
Es un compromiso medido (tabla de umbrales): precisión ≈ 0,94 con ≈ 82 % de cobertura. Con 0,90 la precisión sube a 0,97 pero se pierde casi la mitad de los positivos. Entre 0,35 y 0,70 la salida es «ambiguo» y no se fusiona (el error más caro es mezclar productos distintos).

**4. ¿Dónde falla el modelo?**
En variantes cuando una tienda omite la capacidad en el título (67 % de aciertos). Mejora propuesta: usar las especificaciones de la ficha y entrenar con pares reales.

## Plataforma AIaaS (IE4, IE6)
**5. ¿Por qué no SageMaker?**
Lo intentamos: `CreateModel` fue **denegado por política IAM** del laboratorio (evidencia en `evidencia/sagemaker-intento.txt`) y no hay rol de ejecución. El contenedor habla el mismo contrato (`/ping`, `/invocations`), así que migra sin cambios de código. SageMaker se justificaría con auto-scaling gestionado y monitoreo integrado a mayor escala; para esta carga, EC2 + ASG es más barato (≈ USD 0,04/h por instancia vs ≈ 0,12/h de un `ml.m5.large`).

**6. ¿Cómo demuestran la escalabilidad?**
ALB + Auto Scaling Group (2–4 réplicas, objetivo CPU 50 %). Una instancia satura a ≈ 100 req/s con CPU 77 % (CloudWatch). Con el ASG se mide el escalado bajo carga (ver `evidencia/asg-*.txt`). La API es sin estado: la base es RDS compartida y la cola está en un servidor de servicios.

**7. ¿Qué costo tiene?**
Dos t3.medium + una de servicios + RDS db.t3.micro + ALB ≈ USD 0,15/h. Se destruye con `destruir_asg.sh` al terminar.

## Integración y seguridad (IE7, IE8)
**8. ¿Por qué RabbitMQ y qué pasa si el worker se cae?**
Desacopla la ingesta del cómputo del modelo. Cola durable, mensajes persistentes y *ack* manual: un mensaje a medias se reentrega; tras 3 fallos va a la cola `.dlq`. SQS y Amazon MQ están bloqueados en el laboratorio.

**9. ¿Cómo aseguran la API?**
JWT de Supabase o llave de API (comparación en tiempo constante), límite de tasa **por llamador** (verificado en AWS: 800 peticiones con una llave → 547 × 200 y 253 × 429), validación estricta (422), TLS con CloudFront y puertos internos (RabbitMQ, RDS, modelo) cerrados por grupos de seguridad. Un hallazgo propio: el límite confiaba en `X-Forwarded-For`, falsificable; se corrigió y hay prueba.

**10. ¿Qué encontró la prueba de carga?**
44 errores 500 (11,4 %) en el encolado: `pika.BlockingConnection` no es seguro entre hilos y FastAPI atiende en un pool de hilos. Lo corregimos con un candado y reconexión: 0 fallos en 3 870 peticiones.

## Asistente (agente) (IE5, IE7 de la EP2)
**11. ¿Cómo prioriza el agente sus tareas?**
El plan trae prioridades P1–P3 (consultar preferencias y buscar primero; ofertas e historial después; guardar y responder al final). Si la observación cambia las condiciones (sin resultados, sobre presupuesto, precio alto), **replanifica** y reordena (ver informe, sección 5).

**12. ¿Cómo sabe que el agente decide bien?**
Ejemplos trazados «entrada → decisión → por qué» en el informe: cuando el historial dice «esperar», no guarda la lista y crea una alerta; cuando todo supera el presupuesto, informa cuánto falta. Hay pruebas automatizadas de esos escenarios.

**13. ¿Qué cambió con la unificación chat + agente?**
Una sola ruta (`/chat`, `POST /agent/run`): conversa, compara, razona sobre precios y guarda alertas/listas; muestra tarjetas de los productos consultados y el panel «Cómo pensó». Pendiente: migrar la investigación web y RAG del chat antiguo como herramientas.
