#!/usr/bin/env bash
# Empaqueta el código fuente necesario para construir las imágenes (sin dependencias ni secretos).
set -euo pipefail
cd "$(dirname "$0")/../.."
SALIDA=EP2_ITY1102/infra/.salida
mkdir -p "$SALIDA"
tar -czf "$SALIDA/fuente.tar.gz" \
  --exclude='node_modules' --exclude='.next' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='.env' --exclude='.env.*' --exclude='tsconfig.tsbuildinfo' \
  pyproject.toml README.md alembic.ini app alembic EP2_ITY1102/infra/docker \
  frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/next.config.ts \
  frontend/tsconfig.json frontend/postcss.config.mjs frontend/eslint.config.mjs frontend/components.json \
  frontend/next-env.d.ts frontend/app frontend/components frontend/hooks frontend/lib frontend/types \
  $( [ -d frontend/public ] && echo frontend/public )
ls -lh "$SALIDA/fuente.tar.gz"
