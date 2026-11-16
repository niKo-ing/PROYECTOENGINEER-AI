#!/bin/bash
# Instancia de SERVICIOS: construye las imágenes una vez (y las sube a S3 para que las réplicas escalen rápido),
# crea las tablas en RDS y corre RabbitMQ + worker + un contenedor del modelo.
exec > >(tee /var/log/arranque.log) 2>&1
set -ex
BUCKET=__BUCKET__
dnf install -y docker
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
mkdir -p /opt/app && cd /opt/app
aws s3 cp s3://$BUCKET/fuente.tgz . && tar xzf fuente.tgz
docker build -q -t todobarato-backend -f Dockerfile .
docker build -q -t todobarato-modelo -f EP3_ITY1102/modelo/Dockerfile .
docker save todobarato-backend todobarato-modelo | gzip | aws s3 cp - s3://$BUCKET/images/stack.tar.gz
docker run --rm -e DATABASE_URL='__DB_URL__' todobarato-backend python -c "from app.db import Base, engine; import app.models; Base.metadata.create_all(engine); print('tablas creadas')"
cat > /opt/app/compose.yml <<'YML'
services:
  rabbitmq:
    image: rabbitmq:3.13-management
    restart: unless-stopped
    ports: ["5672:5672"]
    environment: { RABBITMQ_DEFAULT_USER: tb, RABBITMQ_DEFAULT_PASS: "__RABBIT_PASS__" }
  modelo:
    image: todobarato-modelo
    restart: unless-stopped
  worker:
    image: todobarato-backend
    restart: unless-stopped
    command: python -m app.messaging.match_worker
    environment:
      DATABASE_URL: "__DB_URL__"
      RABBITMQ_URL: "amqp://tb:__RABBIT_PASS__@rabbitmq:5672/%2F"
      MATCH_MODEL_URL: http://modelo:8080
      INGESTION_SCHEDULER_ENABLED: "false"
    depends_on: [rabbitmq, modelo]
YML
docker compose -f /opt/app/compose.yml up -d
echo LISTO > /tmp/listo
