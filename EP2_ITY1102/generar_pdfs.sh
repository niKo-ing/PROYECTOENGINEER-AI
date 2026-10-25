#!/usr/bin/env bash
# Genera los PDF de la entrega y muestra un resumen (páginas, figuras, dónde empiezan referencias y anexos).
set -euo pipefail
cd "$(dirname "$0")"
DOC=documento/EP2_Equipo1_Estefania_Tapia_Espinoza.pdf
PRE=defensa/EP2_Presentacion_Equipo1.pdf
chromium --headless --no-sandbox --no-pdf-header-footer --print-to-pdf="$DOC" documento/EP2_ITY1102.html 2>/dev/null
chromium --headless --no-sandbox --no-pdf-header-footer --print-to-pdf="$PRE" defensa/presentacion.html 2>/dev/null
echo "Documento: $(pdfinfo "$DOC" | awk '/Pages/{print $2}') páginas · Presentación: $(pdfinfo "$PRE" | awk '/Pages/{print $2}') diapositivas"
echo "Figuras: $(pdftotext "$DOC" - | grep -oE 'Figura A?[0-9]+\. ' | tr -d '. ' | tr '\n' ' ')"
n=$(pdfinfo "$DOC" | awk '/Pages/{print $2}')
for p in $(seq 1 "$n"); do
  t=$(pdftotext -f "$p" -l "$p" "$DOC" - | grep -m1 -E '^(1\. Intro|Referencias|Anexo A|Anexo B)' || true)
  [ -n "$t" ] && echo "  pág $p: $t"
done
