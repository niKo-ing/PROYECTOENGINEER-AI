#!/usr/bin/env bash
# Prueba de caída abrupta (misma medición que la EP2): consulta la API cada 0,5 s durante 2 minutos
# mientras se apaga un tarro, y cuenta cuántas solicitudes fallaron y cuánto duró la ventana de errores.
#   URL=https://todobarato.cl bash servidor_propio/prueba_caida.sh
# A los 10 s, desenchufe o apague el tarro 1 (o: docker compose stop api web en el tarro 1).
set +e
URL=${URL:-http://localhost}
RUTA=${RUTA:-/api/v1/categories}
DURACION=${DURACION:-130}
OUT="caida-$(date +%H%M).txt"
ok=0; fallas=0; primera=""; ultima=""; inicio=$(date +%s)
echo "Sondeando $URL$RUTA cada 0,5 s durante $DURACION s. Apague un tarro a los 10 s." | tee "$OUT"
while [ $(( $(date +%s) - inicio )) -lt "$DURACION" ]; do
  t=$(( $(date +%s) - inicio ))
  codigo=$(curl -s --max-time 3 -o /dev/null -w '%{http_code}' "$URL$RUTA")
  if [ "$codigo" = 200 ]; then ok=$((ok+1))
  else
    fallas=$((fallas+1)); [ -z "$primera" ] && primera=$t; ultima=$t
    echo "t=${t}s FALLA $codigo" | tee -a "$OUT"
  fi
  sleep 0.5
done
total=$((ok+fallas))
ventana=$([ -n "$primera" ] && echo "$((ultima-primera+1)) s (t=$primera..$ultima)" || echo "0 s")
echo "Solicitudes: $total · fallidas: $fallas · disponibilidad: $(awk "BEGIN{printf \"%.2f %%\", 100*$ok/$total}") · ventana de errores: $ventana" | tee -a "$OUT"
echo "EP2 (AWS, health check 5 s x 2): 5 fallidas de 147 · 96,60 % · ventana 12 s" | tee -a "$OUT"
