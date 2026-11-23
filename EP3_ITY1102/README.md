# EP3 · ITY1102 Arquitectura de Sistemas de IA · TodoBarato AI

Modelo propio de **emparejamiento de productos** («¿estos dos títulos son el mismo producto?») desplegable como contenedor con contrato SageMaker,
API REST segura, mensajería con RabbitMQ, dashboard, pruebas de carga y scripts de despliegue en AWS Academy.

| Carpeta | Contenido |
|---|---|
| `modelo/` | `match_model.joblib`, `metrics.json` (métricas, hiperparámetros, umbrales), `pares_prueba.csv`, `Dockerfile` y `serve` (contrato `/ping` + `/invocations`) |
| `documento/` | Informe técnico: `EP3_Equipo1_Informe.pdf` (10 págs.; fuente `generar.py` → `EP3_ITY1102.html`) |
| `defensa/` | `EP3_Presentacion_Equipo1.pdf` (6 láminas) |
| `diagramas/` | Arquitectura, secuencia del flujo asíncrono y despliegue (PlantUML + PNG) |
| `pruebas/` | `locustfile.py`, `cargar.sh` y `resultados/` (CSV/HTML de Locust, incluida la corrida «antes» de la corrección) |
| `infra/` | `desplegar.sh`/`destruir.sh` (1 instancia), `desplegar_asg.sh`/`destruir_asg.sh` (ALB + Auto Scaling + RDS + CloudFront), `intentar_sagemaker.sh`, `docker-compose.aws.yml` |
| `evidencia/` | Capturas (dashboard) y, tras ejecutar los scripts de AWS, CloudWatch y SageMaker |

Código: `ml/` (características, dataset, entrenamiento, servidor), `app/routers/ml.py` (API), `app/messaging/` (RabbitMQ + worker), `app/ml/` (cliente del modelo y dashboard), pruebas en `tests/modelo_ml/`.

## Ejecutar todo en local (Docker)

```bash
uv venv --python 3.12 .venv && uv pip install -e '.[dev,ml,mensajeria,carga]'
# 1. Datos y entrenamiento (60 productos reales de Paris → pares → modelo + métricas)
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python -c "from app.db import Base, engine; import app.models; Base.metadata.create_all(engine)"
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python scripts/seed_taxonomy.py && DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python scripts/register_paris.py
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python scripts/repopulate_paris.py      # ~3 min
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python -m ml.train
# 2. Pila completa
ML_API_KEYS=clave-local docker compose up --build        # API :8000, modelo :8080, RabbitMQ :15672
```

- Swagger: <http://localhost:8000/docs> · Dashboard: <http://localhost:8000/api/v1/ml/dashboard>
- `curl -XPOST localhost:8000/api/v1/ml/match -H 'x-api-key: clave-local' -H 'content-type: application/json' -d '{"a":"Samsung Galaxy A54 128GB Negro","b":"Celular Galaxy A54 5G 128 GB Negro"}'`
- Carga: `bash EP3_ITY1102/pruebas/cargar.sh http://localhost:8000 local 20 60`
- Pruebas: `DATABASE_URL=sqlite:///./dev_local.db .venv/bin/python -m pytest tests -q` (939 pasan; las del modelo: `tests/modelo_ml`)

## AWS Academy

> **Para la defensa:** guía paso a paso con verificación automática en [`docs/entrega/DEPLOY_DEFENSA.md`](../docs/entrega/DEPLOY_DEFENSA.md).
> `desplegar.sh` ahora también levanta el frontend (puerto 3000: asistente, armador y panel `/observabilidad`) con los
> secretos de la app (`GEMINI_API_KEY`, `AUTH_JWT_SECRET`, `ADMIN_EMAILS`) leídos del entorno.

```bash
# credenciales del lab en el entorno (nunca en el repo)
bash EP3_ITY1102/infra/intentar_sagemaker.sh   # documenta si SageMaker se puede usar (suele fallar por IAM)
bash EP3_ITY1102/infra/desplegar.sh            # S3 + EC2 t3.medium + Compose + alarma CloudWatch (~10-12 min)
bash EP3_ITY1102/infra/verificar_defensa.sh --esperar http://<IP> http://<IP>:3000
bash EP3_ITY1102/pruebas/cargar.sh http://<IP> aws 50 60
bash EP3_ITY1102/infra/destruir.sh             # SIEMPRE al terminar

# Versión escalable (~15 min, ≈ USD 0,15–0,25/h): ALB + ASG 2–4 réplicas (CPU 50 %) + RDS + RabbitMQ/worker + CloudFront HTTPS
bash EP3_ITY1102/infra/desplegar_asg.sh        # imprime las URLs; estado en infra/.salida/asg.env (ignorado por git)
bash EP3_ITY1102/infra/destruir_asg.sh         # SIEMPRE al terminar (y borrar la distribución CloudFront cuando termine de propagar)
```

> **Estado (16-11-2026):** desplegado y medido en AWS Academy (EC2 t3.medium, us-east-1): 0 fallos con 20/50/100 usuarios (≈ 39 → 80 → 102 req/s), CPU máx. 77 % en CloudWatch,
> límite de tasa verificado (547 × 200 / 253 × 429). **SageMaker:** `CreateModel` denegado por IAM del laboratorio (`evidencia/sagemaker-intento.txt`); se usa el mismo contenedor en EC2.
> La IP cambia al reiniciar el laboratorio: ejecutar `desplegar.sh` ~20 min antes de la defensa y `destruir.sh` al terminar.
