# EP2 · ITY1102 Arquitectura de Sistemas de IA · TodoBarato AI

Entrega de la Evaluación Parcial 2: documento técnico (arc42), diagramas, infraestructura desplegable en AWS y material de la defensa.

| Carpeta | Contenido |
|---|---|
| `documento/` | `EP2_ITY1102.html` (fuente) → `EP2_Equipo1_Estefania_Tapia_Espinoza.pdf` |
| `defensa/` | `EP2_Presentacion_Equipo1.pdf` (15 láminas, hecha con la skill canvas-design: fuente en `canvas/presentacion.html`, filosofía en `canvas/filosofia-diseno.md`), `guion.md`, `preguntas_defensa.md` y el video `demo_TodoBaratoAI_AWS.mp4` |
| `diagramas/` | 7 diagramas PlantUML (C4 contexto/contenedores/componentes, patrones, despliegue, 2 secuencias) y sus PNG/SVG |
| `infra/` | Scripts de despliegue en AWS Academy, Dockerfiles de producción, manifiestos de EKS, dashboard, costos |
| `evidencia/` | Capturas y registros del despliegue real (salud, reparto del ALB, failover, carga) |

## Desplegar y borrar (AWS Academy)

Requisitos: AWS CLI con las credenciales del lab en `~/.aws/credentials` (vencen a las 4 h), Docker y el `.env` del proyecto.

```bash
ALERTA_EMAIL=nic.estefania@duocuc.cl bash EP2_ITY1102/infra/desplegar.sh   # ~15 min; el correo debe confirmar la suscripción a las alarmas
bash EP2_ITY1102/infra/estado.sh           # salud, reparto entre zonas, suscripción SNS, alarmas
bash EP2_ITY1102/infra/prueba_carga.sh     # req/s y latencias contra el ALB
bash EP2_ITY1102/infra/demo_failover.sh    # termina una réplica y mide la disponibilidad
bash EP2_ITY1102/infra/destruir.sh         # SIEMPRE al terminar: el ALB y RDS cobran por hora (~USD 0,13/h)
```

Para la defensa: correr `desplegar.sh` ~20 minutos antes, mostrar `http://<ALB>/health` (cambia de instancia y zona al recargar), el dashboard de CloudWatch y `demo_failover.sh`; después `destruir.sh`.

## Qué permite la cuenta (medido el 25-10-2026)

Permitido: EC2 (hasta t3.medium), Auto Scaling, ALB, RDS, S3, SNS, EventBridge, CloudWatch, SSM Parameter Store.
Bloqueado: ECS, EKS, ECR, SQS, Secrets Manager, Bedrock (InvokeModel), crear roles IAM. Único perfil de EC2 usable: `myS3Role` (`s3:*`).
Por eso el despliegue usa EC2 + ASG + Docker con imágenes en S3; el diseño de producción (ECS Fargate como en la EP1, ECR, SQS, Secrets Manager, Cognito, Bedrock) está en el documento, en `infra/ecs/` y, como alternativa, en `infra/kubernetes/` (EKS).

## Generar los PDF

```bash
chromium --headless --no-pdf-header-footer --print-to-pdf=EP2_ITY1102/documento/EP2_Equipo1_Estefania_Tapia_Espinoza.pdf EP2_ITY1102/documento/EP2_ITY1102.html
chromium --headless --no-pdf-header-footer --print-to-pdf=EP2_ITY1102/defensa/EP2_Presentacion_Equipo1.pdf EP2_ITY1102/defensa/presentacion.html
bash EP2_ITY1102/diagramas/renderizar.sh   # si cambian los .puml
```

## Cambios en la aplicación

- `app/main.py`: `INGESTION_SCHEDULER_ENABLED` (las réplicas de la API no programan ingestas) y `/health` informa instancia, zona y rol.
- `app/routers/eventos.py` + `tests/test_eventos.py`: receptor de eventos SNS con verificación de firma (7 pruebas).

## URL de la app

- **HTTPS (usar esta):** https://d1d1jx3qpvm3xv.cloudfront.net/ (CloudFront delante del ALB). El chat y el agente necesitan HTTPS: por HTTP el navegador no expone `crypto.randomUUID`.
- ALB directo (HTTP): http://tb-ep2-alb-1256034381.us-east-1.elb.amazonaws.com/
- Para actualizar las réplicas sin caída después de un cambio: `bash EP2_ITY1102/infra/actualizacion_gradual.sh api` (AWS Academy bloquea instance refresh).
