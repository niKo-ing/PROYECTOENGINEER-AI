# Guion de la defensa · EP2 ITY1102 · Equipo 1 (10 minutos)

Formato: reunión técnica ejecutiva ante arquitectos senior. Hablar de «nosotros decidimos… porque… medimos…».
Cada afirmación importante va con un número medido (IE9: lenguaje técnico; IE10: dominio).

## Antes de entrar (20 min antes)

```bash
bash EP2_ITY1102/infra/desplegar.sh      # solo si se borró; si sigue arriba: bash EP2_ITY1102/infra/estado.sh
```
Dejar abiertas tres pestañas: la app por HTTPS (`https://d1d1jx3qpvm3xv.cloudfront.net/`, con la cuenta de prueba ya logueada), `https://d1d1jx3qpvm3xv.cloudfront.net/health` y el enlace del AWS Pricing Calculator.
Tener una terminal lista con `bash EP2_ITY1102/infra/demo_failover.sh` (plan B: el registro `.salida/failover-*.txt` y la Figura A3).

## Tiempos

| Min | Diapositiva | Quién | Qué decir (ideas clave) |
|---|---|---|---|
| 0:00–0:50 | 00 Portada · 01 Caso · 02 Metas | **Ariel** | «Un mismo producto, tres nombres»: cada tienda publica distinto y comparar es lento. Catálogo canónico + asistente con evidencia + agente de ahorro. Cinco metas medibles: 99,5 %, p95 < 2 s, 2→4 réplicas, RPO 5 / RTO 15 min, < USD 200/mes. |
| 0:50–2:00 | 03 C4 contexto y contenedores · 04 Componentes | **Ariel** | CloudFront → ALB → web, API y worker; RDS, eventos y observabilidad. API **sin estado** (checkpoints en Postgres). Matching híbrido: reglas SKU/MPN/GTIN y LLM solo en ambiguos. |
| 2:00–2:50 | 05 Patrones | **Diego** | Del monolito de la EP1 a tres servicios. **Defecto hallado al desplegar:** con 2 réplicas la ingesta corría 2 veces → worker singleton. Pub/Sub: EventBridge → SNS → worker, mensaje firmado, 202. |
| 2:50–3:50 | 06 Alta disponibilidad | **Diego** | Dos zonas, ninguna indispensable. Medido: el ALB retira la réplica en 12 s, el ASG la repone en 219 s; RPO 5 / RTO 15. Seguridad (SG, TLS, AES-256) y eficiencia (2 réplicas por disponibilidad, no por carga). |
| 3:50–4:40 | 07 Decisiones | **Diego** | Leer la columna «elegido» contra la tachada: GPU 13× más cara, EKS sin necesidad, round robin injusto con solicitudes de 50 ms a 30 s, health check optimizado, HTTPS por el hallazgo del contexto seguro. |
| 4:40–5:40 | 08 Integración | **Nicolás** | Cinco integraciones con su alternativa descartada y su impacto: REST/JSON, eventos (202 en ms), SNS → SQS en producción, adapter de LLM (Gemini → Nova Lite), estado en Postgres. Frameworks: FastAPI, LangGraph, SQLAlchemy, Next.js. |
| 5:40–6:30 | 09 Orquestación y balanceo | **Nicolás** | Tres saltos: usuario → CloudFront (TLS) → ALB (least outstanding requests) → réplica por ruta. Docker multi-etapa; ASG 2–4 por CPU; rolling de a una. **Demo en vivo (30 s):** recargar `/health` y mostrar que cambia de instancia y zona. |
| 6:30–7:15 | 10 Seguridad y monitoreo | **Nicolás** | Capas: HTTPS → JWT/RLS → security groups → TLS + AES-256 → datos. Secretos fuera de la imagen; eventos firmados (403 sin firma). Mostrar el correo de alarma real del failover. |
| 7:15–7:55 | 11 Rendimiento | **Diego** | 43,9 req/s, p95 0,95 s, 0 errores. El cuello de botella es la CPU de la API (54 %), no RDS (15 %): por eso se escala la API. |
| 7:55–8:40 | 12 Failover | **Diego** | Leer la lámina de arriba abajo: retiro planificado sin errores; caída abrupta con 15 s × 3 (ventana 27 s); optimizada a 5 s × 2 (ventana 12 s). Es la optimización medida antes y después. |
| 8:40–9:10 | 13 Costo y recursos | **Diego** | GPU propia USD 734 vs. API USD 55. Sin GPU/TPU porque no se entrena. USD 120,44 en AWS según el Pricing Calculator; ≈ 178 con el LLM, bajo la meta de 200. |
| 9:10–9:30 | 14 Conclusiones | **Nicolás** | Lo que faltó en la EP1 quedó medido; escala, resiste y tiene camino a producción (ECS Fargate, SQS, Secrets Manager, Cognito, Bedrock). |
| 9:30–10:00 | Preguntas | Todos | Responde quien tiene la sección (ver `preguntas_defensa.md`). |

## Frases técnicas útiles (IE9)

- «La API es *stateless*: el estado conversacional vive en Postgres, así el balanceador no necesita *sticky sessions*.»
- «Desacoplamos productor y consumidor con Pub/Sub; en producción agregamos SQS para durabilidad y una DLQ.»
- «El objetivo de escalado es *target tracking* sobre la CPU media del grupo al 60 %.»
- «Medimos el RTO de la capa de aplicación: el ASG repone la réplica en 219 s sin intervención.»
- «La ventana de error de una caída abrupta la define el health check; la acotamos de 27 a 12 segundos.»

## Si algo falla en vivo

- La app no responde: mostrar el video `defensa/demo_TodoBaratoAI_AWS.mp4` (2 min: app, chat, agente, balanceo y failover en vivo) o la sección 10 del documento.
- Las credenciales del lab vencieron: los recursos siguen arriba; la demo de `/health` no necesita la CLI.
