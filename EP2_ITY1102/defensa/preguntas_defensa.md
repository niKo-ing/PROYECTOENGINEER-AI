# Defensa EP2 · Preguntas probables y respuestas (IE10)

Reparto sugerido (cada uno defiende al menos una sección, como pide la pauta):

| Integrante | Sección de la defensa | Indicador |
|---|---|---|
| Ariel Espinoza | 2.1 Caso y objetivos · C4 contexto y contenedores | IE4 |
| Diego Tapia | 2.2 Patrones, alta disponibilidad, decisiones descartadas · 2.4 Optimización | IE4, IE8 |
| Nicolás Estefanía | 2.3 Integración, contenedores, orquestación, balanceo, seguridad y monitoreo · demo en vivo | IE6 |

---

## Arquitectura y patrones (IE4)

**¿Por qué pasaron de monolito modular (EP1) a microservicios?**
Porque la ingesta y la API tienen perfiles de carga distintos. La API escala con los usuarios; la ingesta, con su calendario. Además, al tener más de una réplica de la API, el scheduler interno ejecutaba la ingesta una vez por réplica. Separar el worker resolvió eso. El código es el mismo: cambia cómo se despliega y una variable (`INGESTION_SCHEDULER_ENABLED`).

**¿Son microservicios «de verdad» si comparten la base de datos?**
Son tres servicios desplegables y escalables por separado, enrutados por el ALB. Compartir la base es una decisión consciente para esta etapa (un solo esquema de 3 MB). El siguiente paso, si crece, es separar el esquema de ingesta y comunicar los cambios de precio por eventos.

**¿Dónde está el Event-Driven?**
EventBridge publica `ingesta_programada` cada 6 horas en un tema SNS. SNS entrega el mensaje firmado por HTTP al ALB, que lo enruta solo al worker. El worker verifica la firma, responde 202 y procesa en segundo plano. El productor no conoce al consumidor.

**¿Por qué SNS y no SQS?**
SQS está bloqueado en la cuenta de AWS Academy. En producción usaríamos SNS → SQS: la cola guarda el mensaje si el worker está caído, tiene DLQ y permite escalar workers según la profundidad de la cola.

**¿Qué pasa si se cae una zona de disponibilidad?**
Las réplicas de la API están en `us-east-1a` y `us-east-1b`. El ALB deja de enviar tráfico a la zona caída (health check cada 5 s, 2 fallos; medido: 502 durante ~12 s) y el ASG lanza reemplazos en la zona sana. En la demo matamos una instancia y el servicio siguió respondiendo.

**¿Por qué RDS no está en Multi-AZ en el laboratorio?**
Por presupuesto (USD 20): Multi-AZ duplica el costo de la base. Está en el diseño de producción y en la estimación de costos. La alta disponibilidad de la capa de aplicación sí la demostramos en vivo.

**¿Cuál es su RPO y RTO?**
RPO de 5 minutos (RDS guarda los registros de transacciones cada 5 min y permite restaurar a un punto en el tiempo). RTO de 15 minutos para la base. La capa de aplicación no tiene RTO práctico: sigue respondiendo con una réplica.

## Integración y herramientas (IE6)

**¿Por qué no usaron Kubernetes?**
EKS y ECS están bloqueados en la cuenta, y no se pueden crear roles IAM. Usamos Auto Scaling Groups con Docker, que cumplen el mismo papel: réplicas deseadas, reparto en zonas, autocuración y reemplazo gradual. En producción seguimos con ECS Fargate, como decidimos en la EP1 (definición del servicio en `infra/ecs/`: 2 tareas, autoescalado 2-6 por CPU, circuit breaker con rollback), y dejamos también los manifiestos de EKS como alternativa.

**¿Por qué «least outstanding requests» y no round robin?**
Porque las solicitudes duran muy distinto: el catálogo responde en milisegundos y el agente puede tardar 30 segundos. Round robin seguiría mandando trabajo a una réplica ocupada; este algoritmo elige la que tiene menos solicitudes pendientes.

**¿Por qué el idle timeout del ALB es de 180 s?**
El agente encadena varias llamadas al LLM. Con el valor por defecto (60 s), el ALB cortaría respuestas largas. Es el mismo valor que ya usaba el proxy de Next.js.

**¿Cómo se garantiza la interoperabilidad entre servicios?**
REST/JSON con esquemas Pydantic entre web y API; mensajes JSON firmados entre SNS y el worker; una interfaz común de proveedores de LLM (`app/ai/providers`) para cambiar de Gemini a Bedrock u OpenAI por variable de entorno; y el estado del agente en Postgres, así cualquier réplica continúa una conversación.

**¿Por qué no usan ECR?**
Está bloqueado. Las imágenes se construyen en una EC2 temporal (etapa de build) y se publican en S3; las instancias las bajan al arrancar con el rol `myS3Role`. En producción: ECR con escaneo de vulnerabilidades.

**¿Qué frameworks de IA usan y por qué?**
LangGraph para el agente (grafo de estados con checkpoints: replanifica y retoma), un RAG híbrido propio (léxico + embeddings + reranking) y la API de Gemini. No usamos TensorFlow ni PyTorch porque no entrenamos modelos.

## Recursos y costos (lo que faltó en la EP1)

**¿Por qué no usan GPU?**
No entrenamos ni alojamos modelos. Un modelo abierto en una g5.xlarge (GPU A10G) cuesta USD 734 al mes encendido 24×7; Gemini por API cuesta ≈ USD 55 con nuestra carga estimada. Es 13 veces más barato y no hay que operar la GPU.

**¿Cómo llegaron a 2 réplicas?**
El tráfico pico estimado es de 2 solicitudes por segundo; una réplica soporta bastante más (ver la prueba de carga). Tenemos 2 por disponibilidad, no por carga, y el ASG sube a 4 si la CPU pasa del 60 %.

**¿Por qué cambió el costo de USD 45 (EP1) a USD 178?**
La EP1 no incluía el balanceador, la segunda zona, RDS Multi-AZ, las IPv4 públicas ni el costo del LLM. La cifra nueva incluye todo; la infraestructura en AWS son USD 120,44 según el AWS Pricing Calculator (más USD 1,80 de transferencia). Ojo: la calculadora activa por defecto RDS Proxy y Database Insights (USD 40 extra); los desactivamos porque no los usamos.

**¿Cómo bajarían el costo?**
Savings Plans de 1 año (−30 a −40 % en EC2/RDS), subredes privadas con VPC endpoints para no pagar IPv4 públicas, caché de respuestas del asistente y un modelo más pequeño para detectar la intención.

## Seguridad y monitoreo

**¿Dónde están los secretos?**
La clave de RDS se genera al desplegar y nunca está en el repositorio ni en la imagen. La configuración va cifrada en un bucket S3 privado que solo lee el rol de las instancias. En producción: Secrets Manager con rotación (bloqueado en la cuenta).

**¿Cómo evitan que cualquiera dispare una ingesta llamando al endpoint de eventos?**
El endpoint verifica criptográficamente la firma de SNS, que el certificado venga de `sns.<región>.amazonaws.com` y que el tema sea el nuestro. En las réplicas de la API ni siquiera existe (404). Tiene 7 pruebas automatizadas.

**¿La base de datos es accesible desde internet?**
No. Solo estuvo abierta a la IP de quien desplegó durante la carga inicial de datos; luego el script la cierra. Su security group solo acepta conexiones desde el de la aplicación, y la conexión exige TLS.

**¿Qué alarmas tienen?**
Réplica caída, más de 10 errores 5xx por minuto, latencia media sobre 5 s, CPU de RDS sobre 80 % y memoria de RDS bajo 100 MB. Todas avisan por SNS.

## Optimización (IE8)

**¿Qué métricas usan para decidir si la arquitectura rinde?**
Latencia p95 del backend (meta < 2 s en catálogo), tasa de 5xx (< 1 %), réplicas sanas, CPU del grupo (objetivo de escalado 60 %), conexiones y latencia de RDS, y para la IA: tokens y llamadas a herramientas por consulta.

**¿Qué optimizaciones hicieron?**
Reglas antes que IA en el matching (SKU/MPN/GTIN), máximo 3 herramientas por consulta, presupuesto de 1.600 tokens para el contexto RAG, caché con TTL de investigación, pool de conexiones con pre-ping, dos workers de Uvicorn por réplica e imágenes multi-etapa.
