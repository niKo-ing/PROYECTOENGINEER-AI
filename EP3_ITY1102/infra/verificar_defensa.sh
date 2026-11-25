#!/usr/bin/env bash
# Verifica que la pila desplegada sirva todo lo que se muestra en la defensa.
#
#   bash EP3_ITY1102/infra/verificar_defensa.sh [--esperar] <URL_API> <URL_WEB>
#   bash EP3_ITY1102/infra/verificar_defensa.sh --esperar http://1.2.3.4 http://1.2.3.4:3000
#
# Cuenta de la demo (opcional, desde el entorno; nunca en el repo): DEMO_EMAIL y DEMO_PASSWORD. Si la cuenta no existe, se
# crea. DEMO_EMAIL debe estar en ADMIN_EMAILS del despliegue para abrir el panel. Sin estas variables se omiten las
# pruebas de cuenta, panel y asistente.
# --esperar: reintenta hasta 20 min mientras la instancia construye las imágenes.
# Sale con código 1 si algo falla.
set -uo pipefail

ESPERAR=0
[ "${1:-}" = "--esperar" ] && { ESPERAR=1; shift; }
API=${1:?Uso: verificar_defensa.sh [--esperar] <URL_API> <URL_WEB>}; API=${API%/}
WEB=${2:?Falta la URL del frontend (p. ej. http://IP:3000)}; WEB=${WEB%/}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
FALLAS=0

ok()    { printf '  \033[32m✔\033[0m %s\n' "$*"; }
falla() { printf '  \033[31m✘\033[0m %s\n' "$*"; FALLAS=$((FALLAS + 1)); }
aviso() { printf '  \033[33m!\033[0m %s\n' "$*"; }
# pedir METODO URL [JSON] [TOKEN] → deja el cuerpo en $TMP/cuerpo y devuelve el código HTTP
pedir() {
  local args=(-s -o "$TMP/cuerpo" -w '%{http_code}' --max-time 60 -X "$1" "$2")
  [ -n "${3:-}" ] && args+=(-H 'Content-Type: application/json' --data "$3")
  [ -n "${4:-}" ] && args+=(-H "Authorization: Bearer $4")
  curl "${args[@]}" 2>/dev/null || echo 000
}
campo() { python3 -c "import json,sys; d=json.load(open('$TMP/cuerpo')); print(eval(sys.argv[1], {}, {'d': d}))" "$1" 2>/dev/null; }

if [ "$ESPERAR" = 1 ]; then
  echo "Esperando a que respondan $API/health y $WEB/ (máx. 20 min)…"
  for i in $(seq 1 80); do
    [ "$(pedir GET "$API/health")" = 200 ] && [ "$(pedir GET "$WEB/")" = 200 ] && break
    sleep 15
  done
fi

echo "API ($API)"
[ "$(pedir GET "$API/health")" = 200 ] && ok "/health" || falla "/health no responde 200"
if [ "$(pedir GET "$API/api/v1/ml/health")" = 200 ] && [ "$(campo "d['status']")" = ok ]; then ok "modelo de emparejamiento ($(campo "d['scorer']"))"
else falla "/api/v1/ml/health no está «ok»: $(head -c 200 "$TMP/cuerpo")"; fi
if [ "$(pedir GET "$API/api/v1/pc/components?slot=cpu")" = 200 ] && [ "$(campo "len(d['items'])")" -gt 0 ] 2>/dev/null; then ok "catálogo del armador: $(campo "len(d['items'])") procesadores"
else falla "el catálogo del armador está vacío (la siembra no corrió)"; fi
TIENDAS=$(campo "len([p for p in d['items'] if p.get('store') and p['store'] != 'Precio de referencia'])" 2>/dev/null || echo 0)
REFERENCIA=$(campo "len([p for p in d['items'] if p.get('store') == 'Precio de referencia'])" 2>/dev/null || echo 0)
SIN_PRECIO=$(campo "len([p for p in d['items'] if not p.get('price_clp')])" 2>/dev/null || echo 0)
if [ "${REFERENCIA:-0}" -gt 0 ] 2>/dev/null; then falla "$REFERENCIA procesadores con precio de referencia: producción debe usar solo SoloTodo (PC_CATALOGO=solotodo)"
elif [ "${TIENDAS:-0}" -gt 0 ] 2>/dev/null; then ok "precios de tiendas reales (SoloTodo): $TIENDAS procesadores, $SIN_PRECIO sin stock nuevo"
else aviso "los procesadores aún no tienen precio: la API sincroniza con SoloTodo al minuto de arrancar (o: python -m app.pcbuilder.solotodo)"; fi
[ "$(pedir GET "$API/docs")" = 200 ] && ok "Swagger /docs" || falla "/docs no responde"

if [ -n "${DEMO_EMAIL:-}" ] && [ -n "${DEMO_PASSWORD:-}" ]; then
  CUENTA=$(python3 -c 'import json,os; print(json.dumps({"email": os.environ["DEMO_EMAIL"], "password": os.environ["DEMO_PASSWORD"], "display_name": "Demo defensa"}))')
  LOGIN=$(python3 -c 'import json,os; print(json.dumps({"email": os.environ["DEMO_EMAIL"], "password": os.environ["DEMO_PASSWORD"]}))')
  CODIGO=$(pedir POST "$API/api/v1/auth/login" "$LOGIN")
  [ "$CODIGO" = 200 ] || CODIGO=$(pedir POST "$API/api/v1/auth/register" "$CUENTA")
  TOKEN=$(campo "d['access_token']")
  [ "$CODIGO" = 409 ] && { falla "$DEMO_EMAIL ya existe con otra contraseña: use la contraseña con que la crearon"; TOKEN=""; CODIGO=omitido; }
  if [ -n "$TOKEN" ]; then
    ok "cuenta de la demo (inicio de sesión)"
    CODIGO=$(pedir GET "$API/api/v1/observability/metrics?hours=24" "" "$TOKEN")
    case $CODIGO in
      200) ok "panel de observabilidad: $(campo "d['summary']['runs']") ejecuciones en 24 h" ;;
      403) falla "el panel responde 403: agregue $DEMO_EMAIL a ADMIN_EMAILS y vuelva a desplegar" ;;
      *)   falla "el panel responde $CODIGO" ;;
    esac
    CODIGO=$(pedir POST "$API/api/v1/pc/assistant" '{"messages":[{"role":"user","content":"tengo 700 mil para jugar valorant"}]}' "$TOKEN")
    if [ "$CODIGO" = 200 ] && [ "$(campo "d['state']")" = build ]; then
      if [ "$(campo "d.get('explained_by')")" = llm ]; then ok "asistente: armó un PC y lo explicó Gemini"
      else aviso "asistente: armó un PC, pero sin Gemini (falta GEMINI_API_KEY o se agotó la cuota)"; fi
    else falla "el asistente responde $CODIGO: $(head -c 200 "$TMP/cuerpo")"; fi
  elif [ "$CODIGO" != omitido ]; then
    falla "no se pudo iniciar sesión ni crear la cuenta ($CODIGO; con 500, revise AUTH_JWT_SECRET): $(head -c 200 "$TMP/cuerpo")"
  fi
else
  aviso "sin DEMO_EMAIL/DEMO_PASSWORD: se omiten cuenta, panel y asistente"
fi

echo "Frontend ($WEB)"
for RUTA in / /armar /armar/asistente /mis-pc /guias /observabilidad; do
  [ "$(pedir GET "$WEB$RUTA")" = 200 ] && ok "$RUTA" || falla "$RUTA no responde 200"
done
# Los archivos de Next deben cargar desde fuera (con `next dev` se bloquean y la página queda en «Cargando…»).
pedir GET "$WEB/observabilidad" >/dev/null
CHUNK=$(grep -o '/_next/static/[^"]*\.js' "$TMP/cuerpo" | head -1)
if [ -n "$CHUNK" ] && [ "$(pedir GET "$WEB$CHUNK")" = 200 ]; then ok "archivos de Next (compilación de producción)"
else falla "los archivos de Next no cargan ($CHUNK): reconstruya el frontend en modo producción"; fi
[ "$(pedir GET "$WEB/api/v1/pc/slots")" = 200 ] && ok "el frontend llega a la API (/api/v1)" || falla "el proxy /api/v1 del frontend no llega al backend"

echo
if [ "$FALLAS" = 0 ]; then echo "Todo listo para la defensa."; else echo "$FALLAS verificación(es) fallaron."; exit 1; fi
