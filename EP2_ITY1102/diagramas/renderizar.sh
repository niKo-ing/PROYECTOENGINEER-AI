#!/usr/bin/env bash
# Renderiza todos los .puml de esta carpeta a png/ (y svg/) con la imagen oficial de PlantUML (incluye C4).
set -euo pipefail
cd "$(dirname "$0")"
for formato in png svg; do
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" -w /data plantuml/plantuml:1.2025.4 \
    "-t$formato" -o "$formato" '*.puml'
done
ls -1 png
