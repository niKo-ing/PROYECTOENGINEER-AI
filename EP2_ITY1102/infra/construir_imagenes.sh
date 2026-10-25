#!/usr/bin/env bash
# Construye las imágenes de producción (linux/amd64) y las deja comprimidas en infra/.salida/
# para subirlas a S3 (esta cuenta de AWS Academy no permite ECR).
set -euo pipefail
cd "$(dirname "$0")/../.."          # raíz del repositorio
INFRA=EP2_ITY1102/infra
mkdir -p "$INFRA/.salida"

leer_env() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }

docker build --platform linux/amd64 -f "$INFRA/docker/backend.Dockerfile" -t todobarato-backend:ep2 .
docker build --platform linux/amd64 -f "$INFRA/docker/frontend.Dockerfile" \
  --build-arg NEXT_PUBLIC_SUPABASE_URL="$(leer_env NEXT_PUBLIC_SUPABASE_URL)" \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY="$(leer_env NEXT_PUBLIC_SUPABASE_ANON_KEY)" \
  -t todobarato-frontend:ep2 frontend

docker save todobarato-backend:ep2 | gzip -1 > "$INFRA/.salida/backend.tar.gz"
docker save todobarato-frontend:ep2 | gzip -1 > "$INFRA/.salida/frontend.tar.gz"
ls -lh "$INFRA/.salida/"*.tar.gz
docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep todobarato
