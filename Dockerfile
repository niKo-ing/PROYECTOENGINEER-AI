FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY ml ./ml
COPY EP3_ITY1102/modelo/match_model.joblib EP3_ITY1102/modelo/metrics.json ./EP3_ITY1102/modelo/
COPY alembic ./alembic

RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir '.[ml,mensajeria]'

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
