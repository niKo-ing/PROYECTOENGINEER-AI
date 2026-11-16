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
| `infra/` | `desplegar.sh`, `destruir.sh`, `intentar_sagemaker.sh`, `docker-compose.aws.yml` |
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
ML_API_KEYS=demo-key docker compose up --build        # API :8000, modelo :8080, RabbitMQ :15672
```

- Swagger: <http://localhost:8000/docs> · Dashboard: <http://localhost:8000/api/v1/ml/dashboard>
- `curl -XPOST localhost:8000/api/v1/ml/match -H 'x-api-key: demo-key' -H 'content-type: application/json' -d '{"a":"Samsung Galaxy A54 128GB Negro","b":"Celular Galaxy A54 5G 128 GB Negro"}'`
- Carga: `bash EP3_ITY1102/pruebas/cargar.sh http://localhost:8000 local 20 60`
- Pruebas: `DATABASE_URL=sqlite:///./dev_local.db .venv/bin/python -m pytest tests -q` (939 pasan; las del modelo: `tests/modelo_ml`)

## AWS Academy

```bash
# credenciales del lab en el entorno (nunca en el repo)
bash EP3_ITY1102/infra/intentar_sagemaker.sh   # documenta si SageMaker se puede usar (suele fallar por IAM)
bash EP3_ITY1102/infra/desplegar.sh            # S3 + EC2 t3.medium + Compose + alarma CloudWatch (~6 min)
bash EP3_ITY1102/pruebas/cargar.sh http://<IP> aws 50 60
bash EP3_ITY1102/infra/destruir.sh             # SIEMPRE al terminar
```

> **Estado:** los scripts de AWS están escritos y con la sintaxis verificada, pero todavía **no se ejecutaron** contra la cuenta del laboratorio.
> Todo lo demás (modelo, API, cola, worker, dashboard, carga) se ejecutó y midió en Docker local.
