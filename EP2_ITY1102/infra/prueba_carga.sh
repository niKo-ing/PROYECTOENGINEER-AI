#!/usr/bin/env bash
# Prueba de carga contra el ALB con «hey» (en Docker). Mide req/s y latencias del catálogo y de /health.
#   bash EP2_ITY1102/infra/prueba_carga.sh [segundos] [concurrencia]
source "$(dirname "$0")/comun.sh"
cargar
DUR=${1:-60}; CONC=${2:-20}
OUT="$SALIDA/carga-$(date +%H%M).txt"
correr() {  # correr <nombre> <url>
  echo "=== $1 · $DUR s · concurrencia $CONC · $2" | tee -a "$OUT"
  docker run --rm williamyeh/hey:latest -z "${DUR}s" -c "$CONC" "$2" 2>&1 \
    | grep -E 'Requests/sec|Average|Slowest|Fastest|50%|90%|95%|99%|\[2|\[4|\[5' | tee -a "$OUT"
}
correr salud "http://$ALB_DNS/health"
correr catalogo "http://$ALB_DNS/api/v1/products?limit=20"
correr categorias "http://$ALB_DNS/api/v1/categories"
echo "Resultado en $OUT"
