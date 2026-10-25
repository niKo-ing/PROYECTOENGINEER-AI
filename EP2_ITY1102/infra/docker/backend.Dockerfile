# Imagen de producción del backend (FastAPI + agente LangGraph).
# Se construye desde la raíz del repositorio:
#   docker build -f EP2_ITY1102/infra/docker/backend.Dockerfile -t todobarato-backend .

# --- Etapa 1: instala dependencias en un entorno aislado ---
FROM python:3.12-slim AS deps
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

# --- Etapa 2: imagen final, sin herramientas de compilación ---
FROM python:3.12-slim
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY --from=deps /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
USER app

EXPOSE 8000
# El ALB revisa /health; Docker también, para reiniciar el contenedor si se cuelga.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"

# 2 workers de uvicorn por contenedor (t3.small = 2 vCPU).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2} --proxy-headers --forwarded-allow-ips='*'"]
