#!/usr/bin/env bash
# Despliega TODO en AWS Academy con un solo comando y al final muestra las direcciones.
#
#   bash EP3_ITY1102/infra/desplegar_todo.sh          # despliega, verifica y muestra las URLs (~15-20 min)
#   bash EP3_ITY1102/infra/desplegar_todo.sh --urls   # solo vuelve a mostrar las URLs y si responden
#
# Pide el bloque de credenciales de «AWS Details» (se pega tal cual) y la contraseña de la cuenta de la demo.
# No las guarda en ningún archivo. No borra nada. Funciona también desde fish (se llama con bash).
set -uo pipefail
RAIZ=$(cd "$(dirname "$0")/../.." && pwd); cd "$RAIZ"
INFRA=EP3_ITY1102/infra; SALIDA=$INFRA/.salida
export AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-us-east-1} AWS_PAGER=""

titulo() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
responde() { local c; c=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$1"); [ "$c" = 200 ] && printf '\033[32m✔ responde\033[0m' || printf '\033[31m✘ no responde\033[0m'; }

mostrar_urls() {
  titulo "Direcciones (válidas mientras el laboratorio siga abierto)"
  if [ -f "$SALIDA/estado.env" ]; then
    # shellcheck disable=SC1091
    source "$SALIDA/estado.env"
    printf 'Aplicación:          %-48s %s\n' "$WEB" "$(responde "$WEB/")"
    printf '  Asistente:         %s/armar/asistente\n' "$WEB"
    printf '  Panel:             %s/observabilidad\n' "$WEB"
    printf 'API y Swagger:       %-48s %s\n' "$API/docs" "$(responde "$API/health")"
    printf 'Modelo (dashboard):  %s/api/v1/ml/dashboard   (llave de API: %s)\n' "$API" "$API_KEY"
  else
    echo "Aún no hay un despliegue de la aplicación desde este computador."
  fi
  if [ -f "$SALIDA/asg.env" ]; then
    # shellcheck disable=SC1091
    source "$SALIDA/asg.env"
    printf 'Escalable (ALB):     %-48s %s\n' "http://$ALB_DNS/health" "$(responde "http://$ALB_DNS/health")"
    printf 'Escalable (HTTPS):   %-48s %s\n' "https://$CF_DOMINIO/docs" "$(responde "https://$CF_DOMINIO/health")"
  fi
  echo
  echo "Si dicen «no responde», se cerró la sesión del laboratorio: vuelva a correr este script sin --urls."
}

if [ "${1:-}" = "--urls" ]; then mostrar_urls; exit 0; fi

titulo "Credenciales del laboratorio"
if aws sts get-caller-identity >/dev/null 2>&1; then
  echo "Ya hay credenciales de AWS válidas en esta terminal."
else
  echo "En AWS Academy: Start Lab → punto verde → «AWS Details» → «AWS CLI: Show»."
  echo "Copie el bloque completo (desde [default]), péguelo aquí y presione Enter:"
  unset AWS_PROFILE
  while IFS= read -r linea; do
    linea=${linea//$'\r'/}; linea=${linea// /}
    case "$linea" in
      aws_access_key_id=*)     export AWS_ACCESS_KEY_ID=${linea#*=} ;;
      aws_secret_access_key=*) export AWS_SECRET_ACCESS_KEY=${linea#*=} ;;
      aws_session_token=*)     export AWS_SESSION_TOKEN=${linea#*=} ;;
    esac
    [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] && [ -n "${AWS_SESSION_TOKEN:-}" ] && break
  done
  if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "Esas credenciales no funcionan: copie de nuevo el bloque (vencen al cerrarse la sesión del laboratorio)."; exit 1
  fi
fi
echo "Cuenta de AWS: $(aws sts get-caller-identity --query Account --output text)"

titulo "Datos de la aplicación"
if [ -f .env ]; then set -a; . ./.env; set +a; else echo "AVISO: no hay .env en $RAIZ: el asistente responderá solo con reglas."; fi
[ -n "${GEMINI_API_KEY:-}" ] && echo "Llave de Gemini: cargada desde .env" || echo "AVISO: falta GEMINI_API_KEY en .env"
[ -n "${ADMIN_EMAILS:-}" ] || read -r -p "Correo de la cuenta administradora (entra al panel): " ADMIN_EMAILS
export ADMIN_EMAILS DEMO_EMAIL=${DEMO_EMAIL:-${ADMIN_EMAILS%%,*}}
if [ -z "${DEMO_PASSWORD:-}" ]; then read -rs -p "Contraseña de esa cuenta (se crea si no existe): " DEMO_PASSWORD; echo; fi
export DEMO_PASSWORD
case "${DATABASE_URL:-}" in postgres*) echo "Base de datos: Postgres de DATABASE_URL (fuera del laboratorio)";; *) echo "Base de datos: SQLite en la instancia (se pierde al cerrarse el laboratorio)";; esac

titulo "1/4 Aplicación completa: API, modelo, frontend, asistente y panel (~1 min aquí, ~8 min compilando allá)"
bash "$INFRA/desplegar.sh" || { echo "Falló desplegar.sh: revise el mensaje de arriba."; exit 1; }

titulo "2/4 Versión escalable: ALB + Auto Scaling + RDS + CloudFront (~6 min)"
bash "$INFRA/desplegar_asg.sh" || echo "AVISO: la versión escalable falló (si ya existía en esta sesión, no hace falta repetirla). La aplicación completa sigue."

titulo "3/4 Verificando la aplicación (espera mientras compila)"
# shellcheck disable=SC1091
source "$SALIDA/estado.env"
bash "$INFRA/verificar_defensa.sh" --esperar "$API" "$WEB" || echo "AVISO: alguna verificación falló; revise la lista de arriba."

if [ -f "$SALIDA/asg.env" ]; then
  titulo "4/4 Esperando que respondan el ALB y CloudFront (hasta 15 min)"
  # shellcheck disable=SC1091
  source "$SALIDA/asg.env"
  for _ in $(seq 1 60); do
    a=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://$ALB_DNS/health")
    c=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "https://$CF_DOMINIO/health")
    [ "$a" = 200 ] && [ "$c" = 200 ] && break
    sleep 15
  done
fi

mostrar_urls
echo "Para volver a ver las direcciones:  bash $RAIZ/$INFRA/desplegar_todo.sh --urls"
echo "No cierre el laboratorio (End Lab / Reset) mientras presenta, y no borre nada."
