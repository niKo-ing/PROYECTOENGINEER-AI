# Contenedor del modelo con el contrato de SageMaker: `docker run <imagen> serve` escucha en 8080 (/ping, /invocations).
# Construir desde la raíz del repo:  docker build -f EP3_ITY1102/modelo/Dockerfile -t todobarato-modelo .
FROM python:3.12-slim
WORKDIR /opt/program
RUN pip install --no-cache-dir "scikit-learn>=1.5,<2" "joblib>=1.4,<2" "numpy>=1.26" "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "pydantic>=2"
COPY ml ./ml
COPY EP3_ITY1102/modelo/match_model.joblib /opt/ml/model/match_model.joblib
COPY EP3_ITY1102/modelo/serve /usr/local/bin/serve
RUN chmod +x /usr/local/bin/serve
ENV PYTHONUNBUFFERED=1 MATCH_MODEL_PATH=/opt/ml/model/match_model.joblib
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping', timeout=2)"
CMD ["serve"]
