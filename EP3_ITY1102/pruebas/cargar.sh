#!/usr/bin/env bash
# Uso: cargar.sh <host> <nombre> [usuarios] [segundos]   p. ej.  cargar.sh http://localhost:8000 local 20 60
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST=${1:?host}; NOMBRE=${2:?nombre}; USUARIOS=${3:-20}; SEGUNDOS=${4:-60}
.venv/bin/locust -f EP3_ITY1102/pruebas/locustfile.py --headless -u "$USUARIOS" -r 5 -t "${SEGUNDOS}s" \
  --host "$HOST" --csv "EP3_ITY1102/pruebas/resultados/$NOMBRE" --html "EP3_ITY1102/pruebas/resultados/$NOMBRE.html" --only-summary
