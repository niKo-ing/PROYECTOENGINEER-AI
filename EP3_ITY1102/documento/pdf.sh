#!/usr/bin/env bash
# Regenera el informe y la presentación de EP3 ITY1102 (HTML → PDF con Chromium) y muestra cuántas páginas tienen.
# La pauta pide un informe de 10 páginas y una presentación de máximo 6 láminas.
#   bash EP3_ITY1102/documento/pdf.sh
set -euo pipefail
EP3=$(cd "$(dirname "$0")/.." && pwd)
PY=$(command -v "$EP3/../.venv/bin/python" || command -v python3)
CHROME=$(command -v chromium || command -v chromium-browser || command -v google-chrome)
"$PY" "$EP3/documento/generar.py"
"$PY" "$EP3/defensa/generar.py"
imprimir() { "$CHROME" --headless=new --no-pdf-header-footer --print-to-pdf="$2" "file://$1" 2>/dev/null; }
imprimir "$EP3/documento/EP3_ITY1102.html" "$EP3/documento/EP3_Equipo1_Estefania_Tapia_Espinoza.pdf"
imprimir "$EP3/defensa/presentacion.html" "$EP3/defensa/EP3_Presentacion_Equipo1.pdf"
for f in "$EP3/documento/EP3_Equipo1_Estefania_Tapia_Espinoza.pdf" "$EP3/defensa/EP3_Presentacion_Equipo1.pdf"; do
  echo "$(basename "$f"): $(pdfinfo "$f" | awk '/^Pages/ {print $2}') páginas"
done
