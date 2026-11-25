# EP3 · ITY1102 Arquitectura de Sistemas de IA · TodoBarato AI

**Equipo 1:** Nicolás Estefanía, Diego Tapia y Ariel Espinoza.

Modelo propio de **emparejamiento de productos** («¿estos dos títulos son el mismo producto?») desplegable como contenedor con contrato SageMaker,
API REST segura, mensajería con RabbitMQ, dashboard, pruebas de carga y scripts de despliegue en AWS Academy.

| Carpeta | Contenido |
|---|---|
| `modelo/` | `match_model.joblib`, `metrics.json` (métricas, hiperparámetros, umbrales), `pares_prueba.csv`, `productos.csv` (los 60 productos del dataset), `Dockerfile` y `serve` (contrato `/ping` + `/invocations`) |
| `notebooks/` | **`EP3_ITY1102_Colab.ipynb`** (ejecutado): entrenamiento en Colab, métricas, `model.tar.gz`, inferencia con contrato SageMaker y consumo de la API en AWS. Se regenera con `generar_notebook.py` |
| `documento/` | Informe técnico: `EP3_Equipo1_Estefania_Tapia_Espinoza.pdf` (10 págs.; fuente `generar.py` → `EP3_ITY1102.html`; `bash documento/pdf.sh` regenera informe y presentación) |
| `defensa/` | `EP3_Presentacion_Equipo1.pdf` (6 láminas) |
| `diagramas/` | Arquitectura, secuencia del flujo asíncrono y despliegue (PlantUML + PNG) |
| `pruebas/` | `locustfile.py`, `cargar.sh` y `resultados/` (CSV/HTML de Locust, incluida la corrida «antes» de la corrección) |
| `infra/` | `desplegar_todo.sh` (todo con un comando e imprime las URLs), `desplegar.sh`/`destruir.sh` (1 instancia), `desplegar_asg.sh`/`destruir_asg.sh` (ALB + Auto Scaling + RDS + CloudFront), `intentar_sagemaker.sh`, `capturar_evidencia.sh` (capturas con URL e instancia + gráficos de CloudWatch), `docker-compose.aws.yml` |
| `evidencia/` | Capturas, escalado del ASG, CloudWatch, intento de SageMaker y limpieza del laboratorio. Tras desplegar, `infra/capturar_evidencia.sh` agrega `aws-*.png` (con URL, hora e instancia visibles) y `cw-*.png` |

Código: `ml/` (características, dataset, entrenamiento, servidor), `app/routers/ml.py` (API), `app/messaging/` (RabbitMQ + worker), `app/ml/` (cliente del modelo y dashboard), pruebas en `tests/modelo_ml/`.

## Ejecutar todo en local (Docker)

```bash
uv venv --python 3.12 .venv && uv pip install -e '.[dev,ml,mensajeria,carga]'
# 1. Datos y entrenamiento (60 productos reales de Paris → pares → modelo + métricas)
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python -c "from app.db import Base, engine; import app.models; Base.metadata.create_all(engine)"
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python scripts/seed_taxonomy.py && DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python scripts/register_paris.py
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python scripts/repopulate_paris.py      # ~3 min
DATABASE_URL=sqlite:///./ep3_data.db .venv/bin/python -m ml.train
#    (o sin base ni scraping, con las mismas métricas: .venv/bin/python -m ml.train --productos EP3_ITY1102/modelo/productos.csv)
# 2. Pila completa
ML_API_KEYS=clave-local docker compose up --build        # API :8000, modelo :8080, RabbitMQ :15672
```

- Swagger: <http://localhost:8000/docs> · Dashboard: <http://localhost:8000/api/v1/ml/dashboard>
- `curl -XPOST localhost:8000/api/v1/ml/match -H 'x-api-key: clave-local' -H 'content-type: application/json' -d '{"a":"Samsung Galaxy A54 128GB Negro","b":"Celular Galaxy A54 5G 128 GB Negro"}'`
- Carga: `bash EP3_ITY1102/pruebas/cargar.sh http://localhost:8000 local 20 60`
- Pruebas: `DATABASE_URL=sqlite:///./dev_local.db .venv/bin/python -m pytest tests -q` (1.110 pasan y 5 se omiten sin Gemini/Postgres reales; las del modelo: `tests/modelo_ml`)

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
# destruir.sh y destruir_asg.sh: NO correrlos (piden CONFIRMO_BORRAR=si). Ver «No borrar nada» en docs/entrega/DEPLOY_DEFENSA.md

# Versión escalable (~15 min, ≈ USD 0,15–0,25/h): ALB + ASG 2–4 réplicas (CPU 50 %) + RDS + RabbitMQ/worker + CloudFront HTTPS
bash EP3_ITY1102/infra/desplegar_asg.sh        # imprime las URLs; estado en infra/.salida/asg.env (ignorado por git)
bash EP3_ITY1102/infra/capturar_evidencia.sh   # capturas con URL e instancia + CloudWatch en PNG → evidencia/
bash EP3_ITY1102/documento/pdf.sh              # el informe toma las capturas nuevas
```

**Plataforma AIaaS (por indicación del docente):** SageMaker está bloqueado por IAM en el laboratorio, así que el entrenamiento
gestionado se hace en **Google Colab** (`notebooks/EP3_ITY1102_Colab.ipynb`; en Colab → Secretos, `TODOBARATO_API_URL` y
`TODOBARATO_API_KEY` para que consuma la API desplegada) y la inferencia, en el contenedor con contrato SageMaker sobre EC2 con Auto Scaling.

> **Estado (16-11-2026):** desplegado y medido en AWS Academy (EC2 t3.medium, us-east-1): 0 fallos con 20/50/100 usuarios (≈ 39 → 80 → 102 req/s), CPU máx. 77 % en CloudWatch,
> límite de tasa verificado (547 × 200 / 253 × 429). **SageMaker:** `CreateModel` denegado por IAM del laboratorio (`evidencia/sagemaker-intento.txt`); se entrena en Colab y se usa el mismo contenedor en EC2.
> La IP cambia al reiniciar el laboratorio: ejecutar `desplegar.sh` ~40 min antes de la defensa. **No se destruye al terminar**: la plataforma del laboratorio borró sola la cuenta ~2 h después de cada despliegue (25-10 y 16-11; `evidencia/limpieza-laboratorio.txt`), así que los datos que deban durar van en Supabase, no en la instancia.
