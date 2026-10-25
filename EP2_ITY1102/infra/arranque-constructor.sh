#!/bin/bash
# User data de la EC2 constructora (t3.medium, temporal): construye las imágenes dentro de AWS y las deja en S3.
# Hace de etapa de «build» de CI/CD: el código entra como fuente.tar.gz y sale como imágenes versionadas.
# Al terminar escribe imagenes/LISTO (o imagenes/ERROR con el log) y se apaga (shutdown → terminate).
set -uxo pipefail
BUCKET=__BUCKET__
exec > >(tee /var/log/constructor.log) 2>&1
trap 'aws s3 cp /var/log/constructor.log "s3://$BUCKET/imagenes/constructor.log" --quiet; shutdown -h now' EXIT

fallar() { echo "ERROR: $*"; aws s3 cp /var/log/constructor.log "s3://$BUCKET/imagenes/ERROR" --quiet; exit 1; }

dnf install -y docker || fallar "dnf docker"
systemctl start docker || fallar "docker"
mkdir -p /build && cd /build
aws s3 cp "s3://$BUCKET/fuente/fuente.tar.gz" - | tar -xz || fallar "fuente"
aws s3 cp "s3://$BUCKET/fuente/build.env" build.env || fallar "build.env"
set -a; source build.env; set +a

docker build -f EP2_ITY1102/infra/docker/backend.Dockerfile -t todobarato-backend:ep2 . || fallar "build backend"
docker build -f EP2_ITY1102/infra/docker/frontend.Dockerfile \
  --build-arg NEXT_PUBLIC_SUPABASE_URL="$NEXT_PUBLIC_SUPABASE_URL" \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY="$NEXT_PUBLIC_SUPABASE_ANON_KEY" \
  -t todobarato-frontend:ep2 frontend || fallar "build frontend"

docker save todobarato-backend:ep2 | gzip -1 | aws s3 cp - "s3://$BUCKET/imagenes/backend.tar.gz" || fallar "subir backend"
docker save todobarato-frontend:ep2 | gzip -1 | aws s3 cp - "s3://$BUCKET/imagenes/frontend.tar.gz" || fallar "subir frontend"
docker image ls | aws s3 cp - "s3://$BUCKET/imagenes/LISTO"
