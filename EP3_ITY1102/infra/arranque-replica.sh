#!/bin/bash
# Réplica de la API (Auto Scaling Group): carga las imágenes desde S3 y levanta API + modelo.
exec > >(tee /var/log/arranque.log) 2>&1
set -ex
BUCKET=__BUCKET__
dnf install -y docker
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
for i in $(seq 1 90); do aws s3 ls s3://$BUCKET/images/stack.tar.gz && break; sleep 20; done
aws s3 cp s3://$BUCKET/images/stack.tar.gz - | gunzip | docker load
mkdir -p /opt/app
cat > /opt/app/compose.yml <<'YML'
services:
  modelo:
    image: todobarato-modelo
    restart: unless-stopped
  backend:
    image: todobarato-backend
    restart: unless-stopped
    ports: ["80:8000"]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    environment:
      DATABASE_URL: "__DB_URL__"
      RABBITMQ_URL: "amqp://tb:__RABBIT_PASS__@__SVC_IP__:5672/%2F"
      MATCH_MODEL_URL: http://modelo:8080
      ML_API_KEYS: "__API_KEYS__"
      ML_RATE_LIMIT_PER_MINUTE: "600"
      INGESTION_SCHEDULER_ENABLED: "false"
      APP_ENV: production
    depends_on: [modelo]
YML
docker compose -f /opt/app/compose.yml up -d
